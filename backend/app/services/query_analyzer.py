"""
AI Compass - Query Analyzer
Extracts a QueryProfile from raw query text using heuristic rules.

This is a deterministic keyword-and-length analyzer.
The architecture is designed so a trained ML classifier can replace this module
by implementing the same interface: analyze(query: str) -> QueryProfile
"""
import re
from app.schemas.query import QueryProfile
from app.core.logging import get_logger

logger = get_logger(__name__)

# Keyword sets for task/domain detection
_CODING_KEYWORDS = {
    "code", "function", "class", "algorithm", "debug", "implement", "program",
    "python", "javascript", "java", "c++", "sql", "api", "bug", "error",
    "compile", "runtime", "syntax", "loop", "array", "recursion", "data structure",
    "complexity", "big o", "refactor", "test", "unit test",
}
_MATH_KEYWORDS = {
    "calculate", "solve", "equation", "integral", "derivative", "matrix",
    "probability", "statistics", "proof", "theorem", "formula", "algebra",
    "geometry", "calculus", "linear", "differential",
}
_SCIENCE_KEYWORDS = {
    "physics", "chemistry", "biology", "quantum", "molecule", "atom",
    "experiment", "hypothesis", "theory", "evolution", "genetics", "neuroscience",
}
_MEDICAL_KEYWORDS = {
    "medical", "disease", "symptom", "diagnosis", "treatment", "drug",
    "patient", "clinical", "health", "medicine", "surgery", "therapy",
}
_LEGAL_KEYWORDS = {
    "law", "legal", "contract", "regulation", "compliance", "court",
    "rights", "liability", "statute", "jurisdiction",
}
_CREATIVE_KEYWORDS = {
    "write", "story", "poem", "creative", "fiction", "narrative",
    "character", "plot", "essay", "blog", "article",
}
_SUMMARY_KEYWORDS = {
    "summarize", "summarise", "summary", "summarization", "summarisation",
}
_EDUCATION_KEYWORDS = {
    "teach", "lesson", "tutorial", "learn", "learning", "beginner",
    "walk me through", "step by step",
}
_REASONING_KEYWORDS = {
    "explain", "why", "how does", "analyze", "compare", "evaluate",
    "reason", "argue", "critique", "assess", "implications",
}
_IMAGE_KEYWORDS = {"image", "illustration", "photo", "generate an image", "draw", "poster", "logo"}
_AUDIO_KEYWORDS = {"audio", "transcribe", "speech", "podcast", "music", "voice"}
_VIDEO_KEYWORDS = {"video", "film", "animation", "clip"}
_RESEARCH_KEYWORDS = {"research", "sources", "citations", "literature review", "latest"}
_PRESENTATION_KEYWORDS = {"presentation", "slides", "slide deck"}
_MUSIC_KEYWORDS = {"background music", "song", "soundtrack", "music"}

TASK_TYPE_HINTS = {
    "coding", "research", "creative", "analysis", "math", "image-generation",
    "video-generation", "presentation", "audio-generation", "design", "reasoning", "qa",
    "education", "summarization",
}

_HINT_REQUIREMENTS = {
    "coding": (["text"], ["coding"]),
    "research": (["text"], ["research"]),
    "math": (["text"], ["math"]),
    "image-generation": (["image"], ["image-generation"]),
    "video-generation": (["video"], ["video-generation"]),
    "presentation": (["presentation"], ["presentation"]),
    "audio-generation": (["audio"], ["audio-generation"]),
    "design": (["image"], ["image-generation"]),
    "reasoning": (["text"], ["reasoning"]),
}

_COMPLEXITY_HIGH = {
    "distributed system", "race condition", "deadlock", "concurrency",
    "machine learning", "neural network", "transformer", "optimization",
    "architecture", "design pattern", "microservices", "kubernetes",
    "proof", "theorem", "quantum", "differential equation",
}
_COMPLEXITY_LOW = {
    "what is", "define", "list", "name", "simple", "basic", "hello world",
    "print", "example of",
}

_SENSITIVE_KEYWORDS = {
    "medical", "legal", "financial", "investment", "diagnosis", "treatment",
    "drug", "medication", "law", "contract", "compliance", "security",
    "password", "private", "confidential",
}


def analyze(query: str) -> QueryProfile:
    """
    Analyze the submitted text and return a QueryProfile.
    Replace this function with a trained classifier for production use.
    """
    q = query.lower()
    words = set(re.findall(r'\b\w+\b', q))

    # Task type detection
    task_type = _detect_task_type(q, words)

    # Domain detection
    domain = _detect_domain(q, words)

    # Complexity estimation
    complexity = _estimate_complexity(q, words)

    # Context requirement (longer queries need more context)
    token_estimate = max(64, len(query.split()) * 4)
    context_requirement = min(1.0, token_estimate / 2000)

    # Quality requirement: high for complex/sensitive tasks
    quality_requirement = min(1.0, 0.5 + complexity * 0.3 + (0.2 if domain in {"medical", "legal"} else 0))

    # Risk level: higher for sensitive domains
    risk_level = _estimate_risk(q, words, domain)

    # Latency: coding/interactive tasks prefer low latency
    latency_requirement = 0.7 if task_type in {"coding", "qa"} else 0.5

    # Cost sensitivity: default moderate
    cost_sensitivity = 0.5

    # Reliability: high for critical domains
    reliability_requirement = 0.9 if domain in {"medical", "legal"} else 0.75

    profile = QueryProfile(
        task_type=task_type,
        domain=domain,
        complexity=round(complexity, 3),
        context_requirement=round(context_requirement, 3),
        quality_requirement=round(quality_requirement, 3),
        risk_level=round(risk_level, 3),
        latency_requirement=round(latency_requirement, 3),
        cost_sensitivity=round(cost_sensitivity, 3),
        reliability_requirement=round(reliability_requirement, 3),
        estimated_tokens=token_estimate,
        analysis_method="keyword_rule_analyzer",
        required_modalities=_required_modalities(q, words),
        required_capabilities=_required_capabilities(task_type, q, words),
    )
    logger.debug(f"Query analyzed: task={task_type}, domain={domain}, complexity={complexity:.2f}")
    return profile


def apply_task_type_hint(profile: QueryProfile, task_type_hint: str | None) -> QueryProfile:
    """Apply an explicit UI category without replacing query analysis.

    The original text is still used for domain, complexity, risk and all other
    characteristics; the hint only resolves an intentional task-category
    choice made by the user.
    """
    if not task_type_hint:
        return profile
    hint = task_type_hint.strip().lower()
    if hint not in TASK_TYPE_HINTS:
        raise ValueError(f"Unsupported task category: {task_type_hint}")
    modalities, capabilities = _HINT_REQUIREMENTS.get(hint, (["text"], []))
    return profile.model_copy(update={
        "task_type": hint,
        "required_modalities": modalities,
        "required_capabilities": capabilities,
    })


def _detect_task_type(q: str, words: set) -> str:
    if any(term in q for term in _PRESENTATION_KEYWORDS):
        return "presentation"
    if any(term in q for term in _SUMMARY_KEYWORDS):
        return "summarization"
    if any(term in q for term in _EDUCATION_KEYWORDS):
        return "education"
    if any(term in q for term in _MUSIC_KEYWORDS):
        return "music-generation"
    if any(term in q for term in _IMAGE_KEYWORDS):
        return "image-generation"
    if any(term in q for term in _VIDEO_KEYWORDS):
        return "video-generation"
    if any(term in q for term in _AUDIO_KEYWORDS):
        return "audio-generation"
    if any(term in q for term in _RESEARCH_KEYWORDS):
        return "research"
    if words & _CODING_KEYWORDS:
        return "coding"
    if words & _MATH_KEYWORDS:
        return "math"
    if words & _REASONING_KEYWORDS:
        return "reasoning"
    if words & _CREATIVE_KEYWORDS:
        return "creative"
    return "qa"


def _required_modalities(q: str, words: set) -> list[str]:
    if any(term in q for term in _PRESENTATION_KEYWORDS): return ["presentation"]
    if any(term in q for term in _MUSIC_KEYWORDS): return ["audio"]
    if any(term in q for term in _IMAGE_KEYWORDS): return ["image"]
    if any(term in q for term in _VIDEO_KEYWORDS): return ["video"]
    if any(term in q for term in _AUDIO_KEYWORDS): return ["audio"]
    return ["text"]


def _required_capabilities(task_type: str, q: str, words: set) -> list[str]:
    mapping = {
        "coding": "coding", "math": "math", "reasoning": "reasoning",
        "research": "research", "image-generation": "image-generation",
        "audio-generation": "audio-generation", "video-generation": "video-generation",
        "presentation": "presentation", "music-generation": "music-generation",
    }
    return [mapping[task_type]] if task_type in mapping else []


def _detect_domain(q: str, words: set) -> str:
    if words & _MEDICAL_KEYWORDS:
        return "medical"
    if words & _LEGAL_KEYWORDS:
        return "legal"
    if words & _CODING_KEYWORDS:
        return "computer_science"
    if words & _MATH_KEYWORDS:
        return "mathematics"
    if words & _SCIENCE_KEYWORDS:
        return "science"
    if words & _CREATIVE_KEYWORDS:
        return "creative"
    return "general"


def _estimate_complexity(q: str, words: set) -> float:
    score = 0.4  # baseline
    for phrase in _COMPLEXITY_HIGH:
        if phrase in q:
            score += 0.15
    for phrase in _COMPLEXITY_LOW:
        if phrase in q:
            score -= 0.10
    # Length heuristic
    word_count = len(q.split())
    if word_count > 50:
        score += 0.1
    if word_count > 100:
        score += 0.1
    return max(0.1, min(1.0, score))


def _estimate_risk(q: str, words: set, domain: str) -> float:
    score = 0.15
    if domain in {"medical", "legal"}:
        score += 0.35
    if words & _SENSITIVE_KEYWORDS:
        score += 0.20
    return max(0.05, min(1.0, score))
