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
    AttemptRecord, CandidateScore, EscalationEvent, EvaluationCheck, EvaluationDecision, EvaluationOutcome, ExecutionOutcome, ExecutionPolicy, QueryProfileV2,
)

_NOT_RUN = [
    {"check": "factual_verification", "reason": "No retrieval or fact-checking source is configured, so factual correctness is not established."},
    {"check": "groundedness_citation_check", "reason": "The request supplied no source documents to check the response against."},
    {"check": "independent_evaluator_model", "reason": "No separate evaluator model is configured."},
    {"check": "benchmark_calibration", "reason": "The acceptance rules have not been calibrated against a labelled dataset."},
]


def decide(checks: List[EvaluationCheck], advisory: str = "heuristic_relevance_completeness") -> EvaluationDecision:
    """Accept / Verify / Escalate from the deterministic checks.

    escalate: a required deterministic check failed (the response is unusable as returned).
    verify:   all required checks passed but factual/grounding verification is not available, so the
              response is accepted *unverified*; the advisory heuristic failing also yields verify.
    accept:   only reported when every required check passed AND the advisory heuristic agrees.
    """
    required = [c for c in checks if c.name != advisory]
    failed = [c.name for c in required if not c.passed]
    if failed:
        return EvaluationDecision(action="escalate", rule="required_deterministic_check_failed", reason="Failed: " + ", ".join(failed), failed_checks=failed)
    adv = next((c for c in checks if c.name == advisory), None)
    if adv is not None and not adv.passed:
        return EvaluationDecision(action="verify", rule="advisory_heuristic_disagrees", reason="Required checks passed, but the lexical relevance/completeness heuristic flagged the response; it was not used to reject it.",
                                  pending_checks=[advisory])
    return EvaluationDecision(action="accept", rule="all_available_checks_passed",
                              reason="Every check that was run passed. Factual correctness was not verified (see checks not run).")


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
                             decision=decide(checks), checks_not_run=list(_NOT_RUN),
                             confidence={"model_reported": {"value": None, "source": "unavailable", "note": "The provider adapters do not return a model-reported confidence."},
                                         "evaluator_estimated": {"value": None, "source": "unavailable", "note": "No evaluator model is configured; no confidence percentage is shown."},
                                         "calibrated_probability": False,
                                         "statement": "No calibrated confidence exists. Only the deterministic check outcomes are reported."},
                             judge_model=None, notes=["No evaluation model is configured; relevance/completeness are advisory lexical heuristics and do not affect acceptance or escalation."])


def _legacy(profile: QueryProfileV2):
    from app.services.routing_engine.compat import to_legacy_profile
    return to_legacy_profile(profile)


def execute(*, ranked: List[CandidateScore], models: Dict[str, ModelMetadata], prompt: str, query: str, profile: QueryProfileV2, policy: ExecutionPolicy,
            prompt_source: str, evaluate: bool = True, access_blocked: Optional[Dict[str, str]] = None, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
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
    blocked = access_blocked or {}
    # The first model that can actually be run. A top-ranked model without a credential is a recommendation, not an escalation source.
    first_id = next((c.model_id for c in ranked if c.model_id not in blocked), ranked[0].model_id if ranked else None)
    events: List[EscalationEvent] = []
    last_quality = -1.0

    for idx, cand in enumerate(ranked):
        model = models.get(cand.model_id)
        if model is None or cand.provider.lower() in skipped_providers:
            continue
        if cand.model_id in blocked:
            attempts.append(AttemptRecord(attempt=len(attempts) + 1, model_id=model.model_id, provider=model.provider, outcome="skipped_no_access", note=blocked[cand.model_id]))
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
            prev = next((a for a in reversed(attempts) if a.outcome == "success"), None)
            failed_names = last_eval.decision.failed_checks if last_eval.decision else []
            events.append(EscalationEvent(sequence=len(events) + 1, from_model_id=prev.model_id if prev else first_id or "", to_model_id=model.model_id,
                                          trigger="response_failed_acceptance_checks", detail="Failed: " + (", ".join(failed_names) or "acceptance checks") + f"; escalated to a higher-quality candidate (quality {model.estimated_quality} > {last_quality})",
                                          original_response="retained_as_fallback"))
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
    if events:
        events[-1].outcome = "accepted" if accepted_response else "not accepted; last response returned and flagged"
    outcome.escalation_events = events
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
        if blocked and ranked and ranked[0].model_id in blocked:
            outcome.notes.append(f"Top-ranked model {ranked[0].model_name} was recommended but could not be run ({blocked[ranked[0].model_id]}); the best runnable candidate was used instead.")
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
