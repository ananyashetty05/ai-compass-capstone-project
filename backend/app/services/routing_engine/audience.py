"""Conversational vs developer intent (deterministic lexical rules; every fired rule is reported).

Why a separate stage: a user who asks a question wants an *answer*; a user who says they are building
something wants a *model to integrate*. Recommending developer infrastructure for the first, or a
consumer chatbot for the second, are both wrong. Rules are intentionally conservative: a developer
reading needs one strong signal; otherwise the query stays conversational.
"""
import re
from typing import List

from app.services.routing_engine.types import AudienceAssessment


def _rx(p: str):
    return re.compile(p, re.IGNORECASE)


_STRONG = [
    ("building_an_application", _rx(r"\b(?:building|developing|creating|making|developing)\s+(?:an?\s+|my\s+|our\s+)?(?:\w+\s+){0,3}?(?:app|application|chatbot|bot|product|prototype|startup|saas|website|pipeline|assistant|agent)\b")),
    ("own_project", _rx(r"\b(?:my|our|a|the)\s+(?:college|university|school|capstone|hackathon|side|personal|class|final[- ]year)?\s*(?:project|prototype|startup|app)\b")),
    ("integration_intent", _rx(r"\b(?:integrat\w+|plug (?:it )?into|embed (?:it )?(?:in|into)|use (?:it |them )?(?:in|via|through) (?:my|an?) (?:app|code|api)|rest api|sdk)\b")),
    ("inference_platform_named", _rx(r"\b(?:groq|openrouter|hugging ?face|together ai|fireworks|replicate|inference providers?|model hub)\b")),
    ("open_weights_request", _rx(r"\b(?:open[- ]weights?|open[- ]source (?:models?|llms?)|self[- ]host\w*|run (?:it |them )?locally|on[- ]prem\w*)\b")),
    ("model_shopping_for_a_project", _rx(r"\b(?:suggest|recommend|find|which|what|list|need)\b[^.?!\n]{0,40}\b(?:models?|llms?|apis?)\b[^.?!\n]{0,40}\b(?:integrate|build|use in|for my|for our|can i use|to use)\b")),
]
_EMBED = _rx(r"\b(?:embeddings?|vector (?:search|database|store)|semantic search|rag|retrieval[- ]augmented)\b")
_RERANK = _rx(r"\brerank\w*\b")
_MODEL_WORDS = _rx(r"\b(?:model|models|suggest|recommend|which|choose|select|need|use|using|best|pick|compare)\b")
_FREE = _rx(r"\b(?:free|no[- ]cost|zero[- ]cost|without paying|for free)\b")
_OPEN = _rx(r"\b(?:open[- ]weights?|open[- ]source (?:models?|llms?)|self[- ]host\w*|run (?:it |them )?locally)\b")
_FREE_MODEL = _rx(r"\bfree\b[^.?!\n]{0,30}\b(?:models?|llms?|apis?|tier)\b|\b(?:models?|llms?|apis?)\b[^.?!\n]{0,30}\bfree\b")


def assess(text: str) -> AudienceAssessment:
    signals: List[str] = [name for name, rx in _STRONG if rx.search(text)]
    types: List[str] = []
    if _EMBED.search(text) and _MODEL_WORDS.search(text):
        types.append("embedding")
        signals.append("embedding_model_requested")
    if _RERANK.search(text) and _MODEL_WORDS.search(text):
        types.append("reranker")
        signals.append("reranker_requested")
    developer = bool(signals)
    return AudienceAssessment(
        kind="developer" if developer else "conversational", signals=signals, required_model_types=types,
        prefers_free=bool(developer and _FREE_MODEL.search(text)), requires_open_weights=bool(developer and _OPEN.search(text)))
