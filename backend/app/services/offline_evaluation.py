"""Metadata-only evaluation of model routing strategies."""
from __future__ import annotations

import math
from typing import Optional

from app.schemas.evaluation import OfflineStrategyResult
from app.schemas.model import ModelMetadata
from app.schemas.query import QueryProfile
from app.services import multi_objective_router

AI_COMPASS = "aicompass"
STRONGEST = "strongest"
CHEAPEST = "cheapest"
STATIC = "static"

DATA_DISCLOSURE = (
    "Offline routing evaluation compares model-selection decisions using available "
    "registry and benchmark metadata. It does not generate responses or measure live "
    "inference quality, latency, or provider billing."
)


def _finite(value: object) -> Optional[float]:
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _quality(model: ModelMetadata) -> Optional[float]:
    value = _finite(model.estimated_quality)
    return value if value is not None and 0 <= value <= 1 else None


def _quality_source(model: ModelMetadata) -> Optional[str]:
    if _quality(model) is None:
        return None
    return f"{model.source} · {model.data_provenance}"


def _price_per_million(model: ModelMetadata) -> Optional[float]:
    price = _finite(model.input_price_per_million)
    if price is not None and price >= 0:
        return price
    per_thousand = _finite(model.cost_per_1k_tokens)
    if per_thousand is not None and per_thousand > 0:
        return per_thousand * 1000
    return None


def _estimated_input_cost(model: ModelMetadata, query_profile: QueryProfile) -> Optional[float]:
    price = _price_per_million(model)
    if price is None:
        return None
    return round(query_profile.estimated_tokens * price / 1_000_000, 10)


def _metric_sources(model: ModelMetadata) -> dict[str, Optional[str]]:
    source = f"{model.source} · {model.data_provenance}"
    return {
        "quality": _quality_source(model),
        "pricing": source if _price_per_million(model) is not None else None,
        "latency": source if (_finite(model.avg_latency_seconds) or 0) > 0 else None,
        "reliability": source if _finite(model.reliability) is not None else None,
        "risk": source if _finite(model.risk_level) is not None else None,
        "capabilities": source if model.capabilities else None,
        "context_window": source if model.context_window > 0 else None,
        "availability": source if model.availability else None,
    }


def _result(
    strategy: str,
    model: Optional[ModelMetadata],
    query_profile: QueryProfile,
    *,
    rationale: str,
    routing_score: Optional[float] = None,
) -> OfflineStrategyResult:
    if model is None:
        return OfflineStrategyResult(
            strategy=strategy,
            status="unavailable",
            selection_rationale=rationale,
            constraint_satisfied=False,
            missing_data=["No eligible model could be selected using the available metadata."],
        )

    quality = _quality(model)
    price = _price_per_million(model)
    latency = _finite(model.avg_latency_seconds)
    reliability = _finite(model.reliability)
    risk = _finite(model.risk_level)
    missing = []
    for label, value in (
        ("quality score", quality),
        ("pricing", price),
        ("latency estimate", latency if latency and latency > 0 else None),
        ("reliability", reliability),
        ("risk/privacy attribute", risk),
        ("context window", model.context_window if model.context_window > 0 else None),
    ):
        if value is None:
            missing.append(f"{label.title()} unavailable in registry metadata.")

    return OfflineStrategyResult(
        strategy=strategy,
        status="selected",
        selected_model_id=model.model_id,
        selected_model=model.model_name,
        provider=model.provider,
        selection_rationale=rationale,
        routing_score=routing_score,
        quality_score=quality,
        quality_source=_quality_source(model),
        estimated_cost_usd=_estimated_input_cost(model, query_profile),
        cost_basis=(
            f"Estimated input-only cost for {query_profile.estimated_tokens} analyzer-estimated tokens; "
            "output pricing/usage is not included."
            if price is not None else None
        ),
        input_price_per_million=price,
        latency_seconds=latency if latency is not None and latency > 0 else None,
        reliability_score=reliability,
        risk_score=risk,
        capabilities=list(model.capabilities),
        context_window=model.context_window if model.context_window > 0 else None,
        availability=model.availability,
        constraint_satisfied=True,
        missing_data=missing,
        data_sources=_metric_sources(model),
    )


def evaluate(
    models: list[ModelMetadata],
    query_profile: QueryProfile,
    weights: dict[str, float],
    filtered_out: list[dict[str, str]],
) -> list[OfflineStrategyResult]:
    """Compare four deterministic selection policies over the same candidates."""
    if not models:
        return [
            _result(AI_COMPASS, None, query_profile, rationale="No models passed the shared hard-constraint filter."),
            _result(STRONGEST, None, query_profile, rationale="No eligible models are available for quality ranking."),
            _result(CHEAPEST, None, query_profile, rationale="No eligible models are available for pricing ranking."),
            _result(STATIC, None, query_profile, rationale="No eligible models are available for static ranking."),
        ]

    missing_quality = any(_quality(model) is None for model in models)
    decision = multi_objective_router.route(
        models=models,
        query_profile=query_profile,
        weights=weights,
        filtered_out=filtered_out,
        constraints=None,
    )
    by_id = {model.model_id: model for model in models}
    compass_model = by_id[decision.selected_model_id]
    compass_score = decision.model_scores[0].overall_score
    compass_result = _result(
        AI_COMPASS,
        compass_model,
        query_profile,
        rationale=(
            "Highest multi-objective routing score after shared hard-constraint filtering; "
            "uses the configured routing weights."
        ),
        routing_score=compass_score,
    )
    if missing_quality:
        compass_result = compass_result.model_copy(update={
            "selection_rationale": (
                f"{compass_result.selection_rationale} Quality was unavailable and its dimension "
                "was omitted from scoring for this comparison."
            ),
            "missing_data": [
                *compass_result.missing_data,
                "Quality dimension omitted from adaptive scoring because at least one candidate has no quality score.",
            ],
        })
    results = [compass_result]

    quality_candidates = [(model, _quality(model)) for model in models]
    quality_candidates = [(model, score) for model, score in quality_candidates if score is not None]
    if quality_candidates:
        strongest, strongest_score = min(
            quality_candidates,
            key=lambda item: (-item[1], item[0].model_id),
        )
        strongest_result = _result(
            STRONGEST,
            strongest,
            query_profile,
            rationale=f"Highest available registry quality score ({strongest_score:.3f}); not a live response-quality measurement.",
        )
    else:
        strongest_result = _result(
            STRONGEST,
            None,
            query_profile,
            rationale="Quality ranking unavailable because no eligible model has a usable quality score.",
        )
    results.append(strongest_result)

    priced = [(model, _price_per_million(model)) for model in models]
    priced = [(model, price) for model, price in priced if price is not None]
    if priced:
        cheapest, cheapest_price = min(
            priced,
            key=lambda item: (item[1], item[0].model_id),
        )
        unknown_price_count = len(models) - len(priced)
        caveat = (
            f" Excluded {unknown_price_count} eligible model(s) with unknown pricing."
            if unknown_price_count else ""
        )
        cheapest_result = _result(
            CHEAPEST,
            cheapest,
            query_profile,
            rationale=(
                f"Lowest available input price (${cheapest_price:g} per million tokens)."
                f"{caveat} Estimated request cost excludes output tokens."
            ),
        )
    else:
        cheapest_result = _result(
            CHEAPEST,
            None,
            query_profile,
            rationale="Cheapest-model ranking unavailable because pricing is missing for every eligible model.",
        )
    results.append(cheapest_result)

    static_model = min(models, key=lambda model: (model.fallback_priority, model.model_id))
    results.append(_result(
        STATIC,
        static_model,
        query_profile,
        rationale=(
            "First eligible model by fixed fallback_priority, then model ID for deterministic ties; "
            "independent of user routing weights."
        ),
    ))
    return results
