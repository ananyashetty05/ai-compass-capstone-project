"""Bounded execution with retry, fallback and quality escalation, plus response evaluation.

Safety properties
* Retries apply only to errors the adapter classifies as retryable, with exponential backoff
  and full jitter, and never exceed ``max_retries_per_model``.
* Permanent errors (authentication, invalid model) are never retried; an authentication
  failure also skips the remaining candidates from that provider.
* Total attempts, escalation depth, wall-clock deadline and USD budget are all bounded.
* Quality escalation only moves to a candidate with a *higher* quality estimate and only when
  its estimated cost fits the remaining budget.
* Routing failure (provider errors) and response-quality failure are reported separately.
* Evaluation is deterministic validation plus the existing heuristic; no judge model is
  configured, and the status says so.
"""
import json
import random
import re
import time
from typing import Callable, Dict, List, Optional

from app.schemas.model import ModelMetadata
from app.services.routing_engine.filtering import estimate_request_cost
from app.services.routing_engine.types import (
    AttemptRecord, CandidateScore, EvaluationCheck, EvaluationOutcome, ExecutionOutcome, ExecutionPolicy, QueryProfileV2,
)


def get_adapter_for(model: ModelMetadata):
    from app.services.model_adapters.factory import get_adapter
    return get_adapter(model)


def _error_info(exc: Exception):
    return getattr(exc, "kind", "unavailable"), bool(getattr(exc, "retryable", False))


def evaluate_response(text: str, profile: QueryProfileV2, query: str) -> EvaluationOutcome:
    checks: List[EvaluationCheck] = []
    body = (text or "").strip()
    checks.append(EvaluationCheck(name="non_empty", passed=bool(body), detail="Response has content" if body else "Empty response"))
    refusal = bool(re.match(r"^\s*(i (?:cannot|can't|am unable|'m unable)|sorry, (?:i )?(?:can't|cannot))", body, re.IGNORECASE))
    checks.append(EvaluationCheck(name="not_a_refusal", passed=not refusal, detail="Response opens with a refusal phrase" if refusal else "No refusal opening detected"))
    if profile.structured_output == "json":
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", body, flags=re.IGNORECASE)
        try:
            json.loads(candidate)
            ok, detail = True, "Valid JSON"
        except ValueError as exc:
            ok, detail = False, f"Invalid JSON: {str(exc)[:80]}"
        checks.append(EvaluationCheck(name="valid_json", passed=ok, detail=detail))
    for r in profile.explicit_requirements:
        m = re.match(r"max (\d+) (words|sentences)", r.value) if r.kind == "length_limit" else None
        if m:
            n = int(m.group(1))
            actual = len(body.split()) if m.group(2) == "words" else len(re.findall(r"[.!?](?:\s|$)", body))
            checks.append(EvaluationCheck(name=f"length_{m.group(2)}", passed=actual <= n, detail=f"{actual} {m.group(2)} vs limit {n}"))
    try:
        from app.services import response_evaluator
        legacy = response_evaluator.evaluate(body, query, _legacy(profile))
        scores = {"relevance": legacy.relevance_score, "completeness": legacy.completeness_score, "heuristic_quality": legacy.quality_score}
        checks.append(EvaluationCheck(name="heuristic_relevance_completeness", passed=legacy.accepted, detail="; ".join(legacy.evaluation_reasons)[:200]))
    except Exception:
        scores = {}
    # Only deterministic checks decide acceptance (and therefore escalation, which costs money).
    # The lexical relevance/completeness heuristic is advisory: it is reported but cannot reject a response.
    accepted = all(c.passed for c in checks if c.name != "heuristic_relevance_completeness")
    return EvaluationOutcome(status="completed", method="deterministic_validation_plus_lexical_heuristic", accepted=accepted, checks=checks, heuristic_scores=scores,
                             judge_model=None, notes=["No evaluation model is configured; relevance/completeness are advisory lexical heuristics and do not affect acceptance or escalation."])


def _legacy(profile: QueryProfileV2):
    from app.services.routing_engine.compat import to_legacy_profile
    return to_legacy_profile(profile)


def execute(*, ranked: List[CandidateScore], models: Dict[str, ModelMetadata], prompt: str, query: str, profile: QueryProfileV2, policy: ExecutionPolicy,
            prompt_source: str, evaluate: bool = True, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
            adapter_factory: Optional[Callable[[ModelMetadata], object]] = None, rng: Optional[random.Random] = None) -> tuple:
    """Returns (ExecutionOutcome, EvaluationOutcome)."""
    rng = rng or random.Random()
    adapter_factory = adapter_factory or get_adapter_for  # resolved at call time so it can be substituted in tests
    outcome = ExecutionOutcome(status="failed", mode="execute", prompt_sent_source=prompt_source)
    attempts: List[AttemptRecord] = []
    started = clock()
    spent = 0.0
    skipped_providers: set = set()
    last_eval: Optional[EvaluationOutcome] = None
    accepted_response: Optional[tuple] = None
    quality_fallback: Optional[tuple] = None
    depth = 0
    first_id = ranked[0].model_id if ranked else None
    last_quality = -1.0

    for idx, cand in enumerate(ranked):
        model = models.get(cand.model_id)
        if model is None or cand.provider.lower() in skipped_providers:
            continue
        if len(attempts) >= policy.max_attempts or clock() - started > policy.deadline_seconds:
            outcome.notes.append("Stopped: attempt or time limit reached.")
            break
        est = estimate_request_cost(model, profile.tokens.input_tokens, policy.max_output_tokens)
        if policy.budget_usd is not None and est is not None and spent + est > policy.budget_usd:
            attempts.append(AttemptRecord(attempt=len(attempts) + 1, model_id=model.model_id, provider=model.provider, outcome="skipped_budget", note=f"Estimated ${est:.6f} would exceed the remaining budget"))
            continue
        if policy.budget_usd is not None and est is None:
            attempts.append(AttemptRecord(attempt=len(attempts) + 1, model_id=model.model_id, provider=model.provider, outcome="skipped_budget", note="Cost cannot be estimated, so the budget cannot be enforced"))
            continue
        if idx > 0 and last_eval is not None and last_eval.accepted is False:
            q = model.estimated_quality
            if q is None or q <= last_quality:
                continue  # escalation must move to a higher-quality candidate
            if depth >= policy.max_escalation_depth:
                outcome.notes.append("Stopped: maximum escalation depth reached.")
                break
            depth += 1
        try:
            adapter = adapter_factory(model)
        except Exception as exc:
            kind, retry = _error_info(exc)
            attempts.append(AttemptRecord(attempt=len(attempts) + 1, model_id=model.model_id, provider=model.provider, outcome="provider_unavailable", error_kind=kind, retryable=retry, note="Adapter could not be created"))
            continue
        tries = 0
        text: Optional[str] = None
        while True:
            tries += 1
            t0 = clock()
            try:
                text = adapter.generate(prompt, max_tokens=policy.max_output_tokens)
                usage = adapter.get_usage()
                lat = round((clock() - t0) * 1000, 1)
                it, ot = usage.get("input_tokens"), usage.get("output_tokens")
                cost = None
                if it is not None and ot is not None and model.input_price_per_million is not None and model.output_price_per_million is not None:
                    cost = (it * model.input_price_per_million + ot * model.output_price_per_million) / 1_000_000
                    spent += cost
                attempts.append(AttemptRecord(attempt=len(attempts) + 1, model_id=model.model_id, provider=model.provider, outcome="success", latency_ms=usage.get("latency_ms") or lat, input_tokens=it, output_tokens=ot, cost_usd=cost))
                break
            except Exception as exc:
                kind, retry = _error_info(exc)
                attempts.append(AttemptRecord(attempt=len(attempts) + 1, model_id=model.model_id, provider=model.provider, outcome="error", error_kind=kind, retryable=retry, latency_ms=round((clock() - t0) * 1000, 1)))
                if kind == "authentication":
                    skipped_providers.add(model.provider.lower())
                if retry and tries <= policy.max_retries_per_model and len(attempts) < policy.max_attempts and clock() - started < policy.deadline_seconds:
                    cap = min(policy.max_backoff_seconds, policy.base_backoff_seconds * (2 ** (tries - 1)))
                    sleep(rng.uniform(0, cap))  # full jitter
                    continue
                break
        if text is None:
            continue
        if not evaluate:
            accepted_response = (model, text)
            last_eval = None
            break
        last_eval = evaluate_response(text, profile, query)
        last_quality = model.estimated_quality if model.estimated_quality is not None else last_quality
        if last_eval.accepted:
            accepted_response = (model, text)
            break
        quality_fallback = quality_fallback or (model, text)
        quality_fallback = (model, text)  # keep the most recent (higher-quality) response
        if len(attempts) >= policy.max_attempts:
            break

    outcome.attempts = attempts
    ok_attempts = [a for a in attempts if a.outcome == "success"]
    costs = [a.cost_usd for a in attempts if a.cost_usd is not None]
    outcome.total_cost_usd = round(sum(costs), 8) if costs else None
    outcome.total_latency_ms = round(sum(a.latency_ms or 0 for a in attempts), 1) or None
    chosen = accepted_response or quality_fallback
    if chosen:
        model, text = chosen
        outcome.status = "succeeded"
        outcome.final_model_id, outcome.final_model_name, outcome.response_text = model.model_id, model.model_name, text
        outcome.escalated = model.model_id != first_id
        if outcome.escalated:
            failed_first = [a for a in attempts if a.model_id == first_id and a.outcome == "error"]
            outcome.escalation_reason = "provider_error_fallback" if failed_first else "response_did_not_meet_acceptance_checks"
        if not accepted_response:
            outcome.notes.append("No response passed the acceptance checks; the last response is returned and marked as not accepted.")
    else:
        outcome.status = "budget_exhausted" if attempts and all(a.outcome == "skipped_budget" for a in attempts) else "failed"
        outcome.notes.append("No provider returned a response." if not ok_attempts else "No response was produced.")
    if not evaluate:
        ev = EvaluationOutcome(status="skipped", notes=["Evaluation was not requested."])
    elif last_eval is None:
        ev = EvaluationOutcome(status="unavailable", notes=["No response was produced to evaluate."])
    else:
        ev = last_eval
    return outcome, ev
