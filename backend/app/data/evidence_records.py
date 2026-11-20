"""Application-level evidence store: documented or measured values that override the registry's bare numbers, with source, date, scope and
method. Empty on purpose: no value is fabricated. Add EvidenceRecord entries here (no database migration needed).

    RECORDS["gpt-4.1-mini"] = [EvidenceRecord(metric="quality", value=0.81, unit="0-1 task success", source="<url or paper>", tier=T3,
                                              model_id="gpt-4.1-mini", date="2026-10-01", scope="coding", method="<protocol>", sample_size=500)]
"""
from typing import Dict, List

from app.services.routing_engine.evidence import EvidenceRecord

RECORDS: Dict[str, List[EvidenceRecord]] = {}
