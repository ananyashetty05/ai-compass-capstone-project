"""Query understanding: intent, domain, complexity, requirements, ambiguity, risk, tokens.

Methodology (all deterministic, no external calls):

* Intents are scored from word-boundary lexical evidence. Each pattern family
  contributes ``min(distinct matches, 2) * weight``; scores are normalised by the
  strongest family. Several intents may be reported (primary + secondary).
* Domain is the family with the most distinct evidence; with fewer than two
  pieces of evidence the domain stays ``general`` (no forced classification).
* Complexity is a documented weighted sum of eight bounded features (see
  ``COMPLEXITY_WEIGHTS``). Ambiguity is deliberately *not* a complexity input.
* Token counts are heuristic estimates unless an exact tokenizer is available and
  are always labelled as such.
"""
import math
import re
from typing import Dict, List, Optional, Tuple

from app.services.routing_engine.types import (
    Ambiguity, ComplexityAssessment, Intent, QueryProfileV2, Requirement,
    RiskAssessment, RiskIndicator, TokenEstimate,
)

MAX_QUERY_CHARS = 50_000

# intent -> registry tags that satisfy it (capability or supported-task names)
INTENT_TAGS: Dict[str, Tuple[str, ...]] = {
    "qa": ("qa",), "reasoning": ("reasoning",), "math": ("math",), "coding": ("coding",),
    "debugging": ("coding",), "architecture": ("coding", "reasoning"),
    "writing": ("writing", "creative"), "editing": ("writing",), "creative": ("creative", "writing"),
    "summarization": ("summarization",), "translation": ("translation", "writing"),
    "data_analysis": ("analysis", "data-analysis"), "research": ("research", "analysis"),
    "extraction": ("analysis", "extraction"), "planning": ("reasoning", "planning"),
    "classification": ("analysis", "classification"), "education": ("education", "qa"),
    "image_analysis": ("multimodal", "vision"), "audio_transcription": ("audio",),
    "image_generation": ("image-generation",), "video_generation": ("video-generation",),
    "audio_generation": ("audio-generation",), "music_generation": ("music-generation",),
    "presentation": ("presentation",),
}
# intent -> legacy task_type string used across the existing API/UI
INTENT_TASK_TYPE: Dict[str, str] = {
    "qa": "qa", "reasoning": "reasoning", "math": "math", "coding": "coding", "debugging": "coding",
    "architecture": "coding", "writing": "creative", "editing": "creative", "creative": "creative",
    "summarization": "summarization", "translation": "qa", "data_analysis": "analysis",
    "research": "research", "extraction": "analysis", "planning": "reasoning",
    "classification": "analysis", "education": "education", "image_analysis": "qa",
    "audio_transcription": "audio-generation", "image_generation": "image-generation",
    "video_generation": "video-generation", "audio_generation": "audio-generation",
    "music_generation": "music-generation", "presentation": "presentation",
}
TASK_TYPE_TO_INTENT: Dict[str, str] = {
    "coding": "coding", "research": "research", "creative": "creative", "analysis": "data_analysis",
    "math": "math", "image-generation": "image_generation", "video-generation": "video_generation",
    "presentation": "presentation", "audio-generation": "audio_generation", "design": "image_generation",
    "education": "education", "summarization": "summarization", "reasoning": "reasoning", "qa": "qa",
    "music-generation": "music_generation",
}
# generation intents hard-require a capability and modality
GENERATION_REQUIREMENTS: Dict[str, Tuple[List[str], List[str]]] = {
    "image_generation": (["image-generation"], ["image"]),
    "video_generation": (["video-generation"], ["video"]),
    "audio_generation": (["audio-generation"], ["audio"]),
    "music_generation": (["music-generation"], ["audio"]),
    "presentation": (["presentation"], ["presentation"]),
}

_GEN_VERB = r"(?:generate|create|make|draw|design|render|paint|illustrate|produce|compose|animate)"


def _rx(p: str) -> "re.Pattern":
    return re.compile(p, re.IGNORECASE)


INTENT_PATTERNS: Dict[str, List[Tuple["re.Pattern", float]]] = {
    "coding": [(_rx(r"\b(code|coding|function|class|method|script|programm?(?:ing|er)?|algorithm|api|endpoint|sql|regex|python|javascript|typescript|java|c\+\+|c#|rust|golang|react|node\.?js|django|flask|fastapi|docker|kubernetes|git|unit tests?|refactor|implement(?:ation)?|compile|library|framework|database|cli)\b"), 1.0)],
    "debugging": [(_rx(r"\b(debug\w*|bugs?|stack ?trace|traceback|exceptions?|segfault|segmentation fault|crash(?:es|ing)?|doesn'?t work|not working|stopped working|failing|fails|failed|throws?|how (?:do|can|should) i fix|re-?render\w*|infinite loop|endless(?:ly)?|memory leak|race condition|null ?pointer|off-by-one|undefined is not)\b"), 1.2),
                  (_rx(r"\b\w*error\b"), 0.8), (_rx(r"```"), 0.6)],
    "architecture": [(_rx(r"\b(architecture|system design|design patterns?|microservices?|scalab(?:le|ility)|distributed|high availability|event[- ]driven|schema design|load balanc\w+|fault[- ]tolerant|kafka|replication|message queues?|data pipelines?|order pipelines?)\b"), 1.2)],
    "math": [(_rx(r"\b(prove|proofs?|theorem|lemma|corollary|show that|irrational|rational numbers?)\b"), 2.0),
             (_rx(r"\b(solve|equations?|integral|derivative|matrix|matrices|probability|algebra|geometry|calculus|eigen\w*|differential|factori[sz]e|calculate|compute|mathematic\w*|olympiad|inequalit(?:y|ies)|prime numbers?|primes|fibonacci|number theory|combinatoric\w*|polynomials?|logarithms?|trigonometr\w*|converge\w*|diverge\w*|derive|derivation|closed form|generating functions?)\b"), 1.0),
             (_rx(r"\d\s*[\+\-\*/\^=]\s*[\d(]"), 1.0), (_rx(r"\b[a-z]\s*\^\s*\d"), 1.0)],
    "writing": [(_rx(r"\b(?:write|draft|compose|prepare|create|generate|make|need|send)\b[^.?!\n]{0,30}\b(email|e-mail|letter|essay|blog|article|speech|cover letter|press release|newsletter|memo|report|proposal|post)\b|\b(?:an?|the)\s+(?:formal\s+|short\s+)?(?:email|e-mail|letter|essay|blog post|article|speech|memo)\s+(?:to|about|for|on)\b"), 1.4),
                (_rx(r"\b(draft|compose)\b"), 0.6)],
    "creative": [(_rx(r"\b(story|poem|lyrics?|fiction|narrative|characters?|plot|screenplay|slogan|tagline|brainstorm|creative)\b"), 1.2)],
    "editing": [(_rx(r"\b(proofread|rewrite|rephrase|paraphrase|edit|fix (?:the )?grammar|improve (?:the )?(?:wording|tone|grammar)|make (?:it|this) (?:more )?(?:concise|formal|professional|shorter))\b"), 1.4)],
    "summarization": [(_rx(r"\b(summari[sz]e|summary|summarisation|summarization|tl;?dr|key points|condense|recap|abstract)\b"), 1.6)],
    "translation": [(_rx(r"\b(translate|translation|translating)\b"), 2.0)],
    "data_analysis": [(_rx(r"\b(dataset|data ?frames?|csv|spreadsheet|columns?|rows?|anomal(?:y|ies)|outliers?|regression|correlation|statistic(?:s|al)|pivot|trends?|cohorts?|forecast\w*|a/b test|aggregate)\b"), 1.0)],
    "research": [(_rx(r"\b(research|literature review|sources?|citations?|cite|references|state of the art|survey of|evidence|studies|latest developments)\b"), 1.0)],
    "extraction": [(_rx(r"\b(extract|parse|pull out|named entities|identify all|pull (?:\w+ ){1,4}out)\b"), 1.4)],
    "planning": [(_rx(r"\b(plan|roadmap|schedule|itinerary|strategy|milestones?|timeline)\b"), 1.0),
                (_rx(r"\b(?:study|learning|training|meal|workout|project|migration|rollout) (?:plan|schedule)\b"), 1.6), (_rx(r"\b\d+[- ](?:day|week|month)s?\b"), 0.8)],
    "classification": [(_rx(r"\b(classify|categori[sz]e|sentiment|which category|label (?:each|these|the))\b"), 1.4)],
    "reasoning": [(_rx(r"\b(why|explain|reason(?:ing)?|analy[sz]e|compare|evaluate|assess|argue|critique|implications?|pros and cons|trade-?offs?|justify|derive|infer|deduce|puzzle|logic(?:al)?)\b"), 0.8)],
    "education": [(_rx(r"\b(teach|lesson|tutorial|beginner|eli5|walk me through|for a (?:child|student|beginner|kid)|quiz me|learn)\b"), 1.2),
                  (_rx(r"\bto an? (?:\w+ )?(?:year[- ]old|child|kid|beginner|novice|layperson)\b"), 1.6)],
    "qa": [(_rx(r"\b(?:which|what|suggest|recommend|find|list|compare)\b[^.?!\n]{0,40}\b(?:models?|llms?)\b"), 2.2)],
    "image_generation": [(_rx(r"\b" + _GEN_VERB + r"\b[^.?!\n]{0,40}\b(image|picture|illustration|logo|poster|photo|icon|artwork|portrait|wallpaper|banner)s?\b"), 3.0),
                         (_rx(r"\btext[- ]to[- ]image\b"), 3.0),
                         # a noun-phrase request with no verb ("realistic image of a car", "car image, photorealistic")
                         (_rx(r"\b(?:image|picture|illustration|artwork|render|wallpaper|logo|poster)s?\s+of\b"), 2.2),
                         (_rx(r"\b(?:realistic|photo-?realistic|cartoon|animated|anime|3d|hd)\s+(?:image|picture|photo|illustration|render)s?\b"), 2.2),
                         (_rx(r"\b(?:image|picture|photo|illustration)s?\b[^.?!\n]{0,12}\b(?:realistic|photo-?realistic|cartoon|animated|anime)\b"), 2.2)],
    "video_generation": [(_rx(r"\b" + _GEN_VERB + r"\b[^.?!\n]{0,40}\b(video|film|animation|clip|animated)\b"), 3.0)],
    "audio_generation": [(_rx(r"\b" + _GEN_VERB + r"\b[^.?!\n]{0,40}\b(audio|voice-?over|sound effects?|narration|jingle)\b"), 3.0)],
    "music_generation": [(_rx(r"\b" + _GEN_VERB + r"\b[^.?!\n]{0,40}\b(music|song|soundtrack|melody|beat)\b"), 3.0)],
    "presentation": [(_rx(r"\b(presentation|slide deck|slides|powerpoint|pitch deck)\b"), 3.0)],
    "image_analysis": [(_rx(r"\b(this|the|attached|uploaded)\s+(?:image|photo|picture|screenshot|diagram)\b"), 2.0)],
    "audio_transcription": [(_rx(r"\b(transcribe|transcription|speech[- ]to[- ]text)\b"), 3.0)],
}

DOMAIN_STRONG: Dict[str, "re.Pattern"] = {
    "computer_science": _rx(r"\b(python|javascript|typescript|rust|golang|c\+\+|sql|regex|hash ?map|http|api|algorithm|compiler|segfault|microservices?|kubernetes|docker|concurren\w+|async\w*|crawler|embedding models?|chatbot|open[- ]weights?|llms?|rag|vector (?:search|database)|recursion|data structures?|linked list|binary tree|postgres\w*|mongodb|mysql|redis|nosql|kafka|react|node\.?js|django|jest|git)\b"),
    "mathematics": _rx(r"\b(prove|proofs?|theorem|olympiad|mathematic\w*|prime numbers?|inequalit(?:y|ies)|calculus|algebra|eigen\w*|integral|derivative|fibonacci|generating functions?|equation)\b|\d\s*[\+\-\*/\^]\s*\d"),
    "science": _rx(r"\b(physics|chemistry|biology|quantum|photosynthesis|relativity|boiling point|sky is blue|gravity|molecule|dna|planet|schwarzschild)\b"),
    "education": _rx(r"\b(study plan|curriculum|syllabus|homework|lesson plan)\b"),
    "business": _rx(r"\b(cover letter|resume|job application|business plan|marketing|startup)\b"),
    "creative": _rx(r"\b(short story|poem|novel|screenplay|lyrics)\b"),
}

DOMAIN_PATTERNS: Dict[str, "re.Pattern"] = {
    "computer_science": _rx(r"\b(code|software|algorithm|function|api|database|python|javascript|java|sql|bug|compile|server|frontend|backend|kubernetes|docker|git|programming|devops|machine learning|neural network)\b"),
    "mathematics": _rx(r"\b(equation|integral|derivative|matrix|probability|theorem|proof|algebra|geometry|calculus|statistics|eigen\w*)\b"),
    "science": _rx(r"\b(physics|chemistry|biology|quantum|molecule|atom|experiment|hypothesis|evolution|genetics|neuroscience|astronomy|ecosystem)\b"),
    "medical": _rx(r"\b(medical|disease|symptoms?|diagnos\w+|treatment|medication|patient|clinical|surgery|therapy|dosage|prescri\w+)\b"),
    "legal": _rx(r"\b(law|legal|contract|regulation|compliance|court|liability|statute|jurisdiction|attorney|lawsuit|gdpr)\b"),
    "finance": _rx(r"\b(finance|financial|invest\w*|stock|portfolio|loan|mortgage|tax|revenue|budget|valuation|accounting|trading)\b"),
    "business": _rx(r"\b(business|marketing|customers?|strategy|startup|sales|product roadmap|stakeholders?|kpi|market(?:ing)?)\b"),
    "education": _rx(r"\b(student|teacher|curriculum|lesson|classroom|exam|syllabus|homework|school)\b"),
    "creative": _rx(r"\b(story|poem|novel|fiction|lyrics|screenplay|character|plot|artwork|design)\b"),
}

COMPLEXITY_WEIGHTS: Dict[str, float] = {
    "subtasks": 0.13, "constraints": 0.09, "reasoning_depth": 0.17, "technical_depth": 0.11, "context_size": 0.08,
    "intent_breadth": 0.06, "output_demand": 0.05, "structured_output": 0.03,
    "difficulty_markers": 0.08, "precision": 0.06, "domain_specificity": 0.06, "consequence": 0.08,
}
# Score thresholds for the weighted sum. Floors (see _FLOORS) can only raise a band, never lower it.
COMPLEXITY_BANDS = (("simple", 0.15), ("moderate", 0.30), ("complex", 0.48))
_ACTION_VERBS = _rx(r"\b(analy[sz]e|identify|explain|compare|write|implement|list|summari[sz]e|design|evaluate|generate|create|build|fix|calculate|derive|prove|plan|extract|translate|convert|optimi[sz]e|review|recommend|describe|detect|report)\b")
_CONSTRAINT_MARKERS = _rx(r"\b(must|should|only|exactly|at most|at least|no more than|without|avoid|do not|don'?t|ensure|limit|never|always|required?)\b|\b(?:under|within|in)\s+\d+\s+(?:words|sentences|bullets|lines|paragraphs)\b")
_REASONING_CUES = _rx(r"\b(prove|derive|trade-?offs?|justify|step[- ]by[- ]step|edge cases?|invariants?|complexity analysis|optimi[sz]e|compare|why|root cause|rigorous|formal(?:ly)?)\b")
_TECH_TERMS = _rx(r"\b(distributed systems?|concurren\w+|race conditions?|deadlocks?|transformers?|consensus|kubernetes|compiler|cryptograph\w+|differential equations?|bayesian|eigen\w*|neural networks?|machine learning|microservices?|sharding|big o|lock-?free|linearizab\w+|gradient|async\w*|rate[- ]limit\w*|exponential backoff|idempot\w+|multi-?thread\w*|parallel\w*|oauth|websockets?|general relativity|schwarzschild|generating functions?)\b")
_DIFFICULTY_MARKERS = _rx(r"\b(hard|difficult|challenging|olympiad|advanced|rigorous\w*|research[- ]level|non-?trivial|graduate[- ]level|phd|from first principles|formal(?:ly)?|exhaustive\w*)\b")
_PROOF_CUES = _rx(r"\b(prove|proof|derive|derivation|show that|demonstrate that)\b")
_STRONG_REASONING_CUES = _rx(r"\b(prove|derive|rigorous\w*|step[- ]by[- ]step|each step|justify|formal(?:ly)?|trade-?offs?|linearizab\w+)\b")
_PRECISION_MARKERS = _rx(r"\b(accurate\w*|precise\w*|exact\w*|correct\w*|rigorous\w*|verify|double[- ]check|no mistakes|production[- ]ready)\b")
_REGULATED = {"medical": 1.0, "legal": 1.0, "finance": 0.8, "science": 0.4, "mathematics": 0.4, "computer_science": 0.3}
_ENUM_SPLIT = _rx(r",\s*(?:and\s+|or\s+)?|\s+(?:and|plus|as well as)\s+")

_LENGTH_RX = _rx(r"\b(?:under|within|less than|at most|no more than|no longer than|not exceed|not to exceed|must not exceed|max(?:imum)?(?: of)?|up to)\s+(\d{1,5})\s*(words|sentences|characters|tokens|lines|paragraphs|bullets|slides)\b")
_EXACT_LEN_RX = _rx(r"\b(?:in|exactly|about|around)\s+(\d{1,4})\s+(words|sentences|bullets|bullet points|paragraphs|slides)\b")
_LANG_CODE_RX = _rx(r"\b(python|javascript|typescript|java|c\+\+|c#|rust|golang|sql|bash|php|ruby|kotlin|swift|matlab)\b")
_LANG_HUMAN_RX = _rx(r"\b(?:in|into|to)\s+(spanish|french|german|hindi|japanese|chinese|korean|italian|portuguese|arabic|russian)\b")
_FORMAT_RXS: List[Tuple[str, "re.Pattern"]] = [
    ("json", _rx(r"\b(json)\b")), ("table", _rx(r"\b(?:markdown |a )?tables?\b")),
    ("bullets", _rx(r"\bbullet(?:ed)?(?: points| list)?\b")), ("csv", _rx(r"\b(?:as|in|to|into|output|return|format)\s+(?:a\s+)?csv\b")), ("yaml", _rx(r"\b(?:as|in|to|into|output|return|format)\s+(?:a\s+)?yaml\b")),
]

_SECRET_RXS: List[Tuple["re.Pattern", str]] = [
    (_rx(r"\b(?:sk|pk|rk)-[A-Za-z0-9_\-]{16,}\b"), "api_key"),
    (_rx(r"\bAKIA[0-9A-Z]{16}\b"), "cloud_key"),
    (_rx(r"\bghp_[A-Za-z0-9]{30,}\b"), "vcs_token"),
    (_rx(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private_key"),
    (_rx(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}"), "jwt"),
    (_rx(r"\b(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*\S{6,}"), "assigned_secret"),
]
_EMAIL_RX = _rx(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b")
_PHONE_RX = re.compile(r"(?<![\d.])(?:\+\d{1,3}[ -]?)?(?:\(\d{3}\)|\d{3})[ -]\d{3}[ -]\d{4}(?!\d)")
_SSN_RX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_AADHAAR_RX = re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")
_CARD_RX = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_FIN_RX = _rx(r"\b(bank account|iban|routing number|credit card|salary|invoice|tax return|portfolio|mortgage|loan)\b")
_MED_RX = _rx(r"\b(diagnos\w+|symptoms?|medications?|dosage|prescri\w+|patient|treatment plan|lab results?)\b")
_LEGAL_RX = _rx(r"\b(lawsuit|liability|legal advice|attorney|nda|gdpr|contract (?:dispute|clause))\b")
_SECURITY_RX = _rx(r"\b(exploit|vulnerabilit\w+|penetration test|malware|ransomware|phishing|zero-day|sql injection)\b")
_CONFIDENTIAL_RX = _rx(r"\b(confidential|internal use only|proprietary|trade secret|do not share|keep (?:this )?private|on[- ]prem(?:ises)?)\b")


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def estimate_tokens(text: str) -> Tuple[int, str, bool]:
    """Return (tokens, method, exact). Uses tiktoken when importable, otherwise chars/4."""
    try:  # optional dependency, never required
        import tiktoken  # type: ignore
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text)), "tiktoken_cl100k_base_approximation_for_other_providers", False
    except Exception:
        return max(1, math.ceil(len(text) / 4)), "heuristic_chars_div_4", False


# ── intents ─────────────────────────────────────────────────────────────────

def _score_intents(text: str) -> Dict[str, float]:
    raw: Dict[str, float] = {}
    for name, patterns in INTENT_PATTERNS.items():
        total = 0.0
        for rx, weight in patterns:
            distinct = {m.group(0).lower() for m in rx.finditer(text)}
            total += min(len(distinct), 2) * weight
        if total > 0:
            raw[name] = total
    return raw


def _classify_intents(text: str) -> Tuple[List[Intent], float]:
    raw = _score_intents(text)
    if not raw:
        return [Intent(name="qa", score=0.4, registry_tags=list(INTENT_TAGS["qa"]))], 0.35
    # generation intents dominate: they determine modality and hard requirements
    gen = {k: v for k, v in raw.items() if k in GENERATION_REQUIREMENTS or k == "audio_transcription"}
    ordered = sorted(raw.items(), key=lambda kv: (-kv[1], kv[0]))
    if gen:
        top_gen = max(gen.items(), key=lambda kv: (kv[1], kv[0]))[0]
        ordered = [(top_gen, raw[top_gen])] + [kv for kv in ordered if kv[0] != top_gen]
    top = ordered[0][1]
    # coding verbs like "write a function" must not be double counted as writing
    intents: List[Intent] = []
    for name, score in ordered:
        if score >= 0.45 * top and score >= 0.8:
            intents.append(Intent(name=name, score=round(min(1.0, score / top), 3), registry_tags=list(INTENT_TAGS[name])))
    if intents and intents[0].name in {"coding", "debugging"}:
        intents = [i for i in intents if i.name not in {"writing", "reasoning"} or i.score >= 0.9]
    if not intents:
        intents = [Intent(name=ordered[0][0], score=1.0, registry_tags=list(INTENT_TAGS[ordered[0][0]]))]
    second = ordered[1][1] if len(ordered) > 1 else 0.0
    confidence = round(min(0.95, 0.45 + 0.5 * (top - second) / (top + 0.5)), 3)
    return intents[:4], confidence


def _classify_domain(text: str) -> Tuple[str, float]:
    counts = {d: len({m.group(0).lower() for m in rx.finditer(text)}) for d, rx in DOMAIN_PATTERNS.items()}
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    best, n = ranked[0]
    if n < 2:
        # A single hit is accepted for regulated domains, or when it is a specific term that belongs to one domain only.
        if n == 1 and best in {"medical", "legal"}:
            return best, 0.5
        strong = sorted(d for d, rx in DOMAIN_STRONG.items() if rx.search(text))
        if len(strong) == 1:
            return strong[0], 0.45
        if len(strong) > 1 and n == 1 and best in strong:
            return best, 0.4
        return "general", round(0.3 if n == 0 else 0.35, 3)
    runner = ranked[1][1]
    return best, round(min(0.95, 0.5 + 0.45 * (n - runner) / (n + 1)), 3)


# ── requirements / structure ────────────────────────────────────────────────

def _extract_requirements(text: str, tokens: int) -> Tuple[List[Requirement], List[Requirement], Optional[str]]:
    explicit: List[Requirement] = []
    inferred: List[Requirement] = []
    structured: Optional[str] = None

    def add(kind: str, value: str, ev: str) -> None:
        explicit.append(Requirement(kind=kind, value=value, origin="explicit", evidence=ev))

    for m in _LANG_CODE_RX.finditer(text):
        add("programming_language", m.group(1).lower(), "phrase naming a programming language")
    for m in _LANG_HUMAN_RX.finditer(text):
        add("output_language", m.group(1).lower(), "phrase naming a human language")
    for kind, rx in _FORMAT_RXS:
        if rx.search(text):
            add("output_format", kind, f"mentions {kind}")
            structured = structured or kind
    for m in _LENGTH_RX.finditer(text):
        add("length_limit", f"max {m.group(1)} {m.group(2).lower()}", "explicit upper bound")
    for m in _EXACT_LEN_RX.finditer(text):
        add("length_target", f"{m.group(1)} {m.group(2).lower()}", "explicit size")
    if _rx(r"\b(one|a single) sentence\b").search(text):
        add("length_target", "1 sentence", "explicit size")
    if _rx(r"\b(brief(?:ly)?|concise(?:ly)?|short|tl;?dr)\b").search(text):
        add("length_preference", "short", "asks for brevity")
    if _rx(r"\b(detailed|comprehensive|in[- ]depth|thorough|long-form)\b").search(text):
        add("length_preference", "long", "asks for detail")
    if _rx(r"\b(cite|citations?|sources?|references|with links)\b").search(text):
        add("citations", "requested", "mentions sources or citations")
    if _rx(r"\b(accurate|accurately|precise|precisely|verify|double[- ]check|rigorous)\b").search(text):
        add("accuracy", "high", "stresses accuracy")
    if _rx(r"\b(most accurate|highest[- ](?:quality|accuracy)|best (?:possible )?(?:quality|accuracy)|most (?:capable|reliable|powerful)|state[- ]of[- ]the[- ]art|best model)\b").search(text):
        add("accuracy", "highest", "asks for the most accurate / highest-quality option")
    if _rx(r"\b(as (?:quickly|fast) as possible|fastest|lowest latency|asap|right away|immediately)\b").search(text):
        add("latency", "lowest", "asks for the fastest option")
    if _rx(r"\b(cheapest|lowest[- ](?:cost|price)|as cheap(?:ly)? as possible|minimi[sz]e (?:the )?cost|least expensive)\b").search(text):
        add("cost", "lowest", "asks for the cheapest option")
    if _rx(r"\b(quickly|quick|asap|as fast as possible|immediately|right away)\b").search(text):
        add("latency", "low", "asks for speed")
    if _rx(r"\b(cheap(?:est)?|low[- ]cost|budget|inexpensive|free)\b").search(text):
        add("cost", "low", "asks for low cost")
    if _CONFIDENTIAL_RX.search(text):
        add("privacy", "restricted", "marks content as confidential/private")
    if _rx(r"\b(latest|today|current(?:ly)?|news|real[- ]time|as of now|this week)\b").search(text):
        inferred.append(Requirement(kind="external_information", value="possibly required", origin="inferred",
                                    evidence="time-sensitive wording; no registry model declares live web access"))
    if tokens > 8000:
        inferred.append(Requirement(kind="long_context", value=f"~{tokens} input tokens", origin="inferred", evidence="input size estimate"))
    return explicit, inferred, structured


def _detect_ambiguities(text: str, words: int, has_content_block: bool, intents: List[Intent],
                        explicit: List[Requirement]) -> List[Ambiguity]:
    out: List[Ambiguity] = []
    names = {i.name for i in intents}
    if words < 3 and not has_content_block:
        out.append(Ambiguity(kind="too_short", severity="major",
                             message="The request is too short to determine what is being asked.",
                             clarifying_question="What would you like the model to do, and with what input?"))
    elif words <= 5 and not has_content_block and names <= {"qa"}:
        out.append(Ambiguity(kind="unclear_objective", severity="minor",
                             message="No clear task was detected; the request is treated as a general question."))
    if not has_content_block and _rx(r"^\s*(?:please\s+)?(fix|debug|explain|summari[sz]e|translate|improve|review|rewrite|proofread|analy[sz]e|edit)\s+(this|that|it|these|the above|the following)\b").search(text) and words < 40:
        out.append(Ambiguity(kind="missing_referent", severity="major",
                             message="The request refers to content (\"this\", \"the following\") that is not included.",
                             clarifying_question="Paste the content you want the model to work on."))
    if not has_content_block and _rx(r"\b(attached|attachment|uploaded|this file|the file|this image|the image|this pdf|the document|this dataset|the dataset)\b").search(text):
        out.append(Ambiguity(kind="missing_attachment", severity="major",
                             message="The request mentions an attachment, but this endpoint accepts text only.",
                             clarifying_question="Paste the relevant text or data into the query."))
    vals = {(r.kind, r.value) for r in explicit}
    if ("length_preference", "short") in vals and ("length_preference", "long") in vals:
        out.append(Ambiguity(kind="contradiction", severity="minor", message="The request asks for both a brief and a detailed answer.",
                             clarifying_question="Should the answer be brief or detailed?"))
    fmts = {r.value for r in explicit if r.kind == "output_format"}
    if len(fmts & {"json", "table", "bullets", "yaml", "csv"}) > 1:
        out.append(Ambiguity(kind="contradiction", severity="minor", message="Several output formats are requested (" + ", ".join(sorted(fmts)) + ").",
                             clarifying_question="Which single output format should be used?"))
    if _rx(r"\bformal\b").search(text) and _rx(r"\b(casual|informal|chatty)\b").search(text):
        out.append(Ambiguity(kind="contradiction", severity="minor", message="Both formal and casual tone are requested."))
    if names & {"writing", "creative", "editing"} and not any(r.kind.startswith("length") for r in explicit) and words >= 3:
        out.append(Ambiguity(kind="unspecified_output", severity="minor", message="No length or audience was specified for the writing task."))
    return out


# ── complexity / risk ───────────────────────────────────────────────────────

def _enumerated_requirements(text: str) -> int:
    """Items in 'with/including/that X, Y and Z' lists: each is an extra requirement the answer must satisfy."""
    best = 0
    for m in re.finditer(r"\b(?:with|including|includes|covering|featuring|plus|supporting|that (?:has|handles|supports))\b([^.?!\n]{3,200})", text, re.I):
        parts = [p for p in _ENUM_SPLIT.split(m.group(1)) if p and p.strip()]
        best = max(best, len(parts))
    return best


def _assess_complexity(text: str, intents: List[Intent], tokens: int, out_tokens: int, structured: Optional[str],
                       domain: str = "general", risk_score: float = 0.0) -> ComplexityAssessment:
    primary = intents[0].name
    numbered = len(re.findall(r"(?m)^\s*(?:\d+[.)]|[-*•])\s+\S", text))
    verbs = len({m.group(0).lower() for m in _ACTION_VERBS.finditer(text)})
    enum_items = _enumerated_requirements(text)
    subtasks = min(1.0, max(numbered, verbs - 1, enum_items - 1, 0) / 4.0)
    constraints = min(1.0, len(_CONSTRAINT_MARKERS.findall(text)) / 6.0)
    strong = len({m.group(0).lower() for m in _STRONG_REASONING_CUES.finditer(text)})
    base = {"math": 0.45, "architecture": 0.45, "reasoning": 0.3, "debugging": 0.25, "planning": 0.2, "research": 0.25, "coding": 0.1}.get(primary, 0.0)
    reasoning = min(1.0, base + 0.25 * len(_REASONING_CUES.findall(text)) + 0.15 * strong)
    tech_terms = len({m.group(0).lower() for m in _TECH_TERMS.finditer(text)})
    technical = min(1.0, tech_terms / 3.0)
    context = min(1.0, tokens / 6000.0)
    breadth = min(1.0, (len(intents) - 1) / 3.0)
    output = min(1.0, out_tokens / 2000.0)
    struct = 1.0 if structured in {"json", "yaml", "csv", "table"} else 0.0
    markers = len({m.group(0).lower() for m in _DIFFICULTY_MARKERS.finditer(text)})
    difficulty = min(1.0, 0.45 * markers)
    precision = min(1.0, (0.5 if primary in {"math", "coding", "debugging", "data_analysis", "extraction"} else 0.0) + 0.3 * len(_PRECISION_MARKERS.findall(text)))
    specificity = _REGULATED.get(domain, 0.0)
    consequence = min(1.0, risk_score)
    comps = {"subtasks": subtasks, "constraints": constraints, "reasoning_depth": reasoning, "technical_depth": technical,
             "context_size": context, "intent_breadth": breadth, "output_demand": output, "structured_output": struct,
             "difficulty_markers": difficulty, "precision": precision, "domain_specificity": specificity, "consequence": consequence}
    score = round(sum(COMPLEXITY_WEIGHTS[k] * v for k, v in comps.items()), 4)

    def band_of(x: float) -> str:
        for name, hi in COMPLEXITY_BANDS:
            if x < hi:
                return name
        return "highly_complex"
    cat = band_of(score)
    order = ["simple", "moderate", "complex", "highly_complex"]
    adjustments: List[str] = []

    def floor(band: str, why: str) -> None:
        nonlocal cat
        if order.index(band) > order.index(cat):
            adjustments.append(f"raised to {band}: {why}")
            cat = band
    # Floors: a short request can be very hard. These rules encode that explicitly rather than hiding it in a weight.
    proofs = len(_PROOF_CUES.findall(text))
    if primary == "math" and proofs:
        floor("highly_complex" if strong >= 3 else "complex", f"a proof/derivation is requested ({strong} strong reasoning cue(s))")
    if markers >= 2:
        floor("complex", "the request itself describes the task as hard/advanced/rigorous")
    elif markers == 1 and primary == "math":
        floor("moderate", "a mathematical task is flagged as hard")
    if primary in {"coding", "architecture", "debugging"} and enum_items >= 3:
        floor("complex" if (tech_terms >= 1 or markers) else "moderate", f"{enum_items} enumerated requirements" + (" with technical depth" if tech_terms else ""))
    if primary in {"coding", "architecture"} and tech_terms >= 2 and strong >= 1:
        floor("complex", "several advanced technical terms combined with a formal reasoning requirement")
    if primary == "architecture":
        floor("complex", "system design requires weighing several interacting constraints")
    if domain in {"medical", "legal", "finance"} and primary in {"reasoning", "research", "planning"}:
        floor("complex", f"regulated domain ({domain}) where an error has material consequences")
    elif domain in {"medical", "legal", "finance"} and risk_score >= 0.5:
        floor("moderate", f"regulated domain ({domain}) with sensitive content")
    if primary == "research":
        floor("complex", "research requires gathering and weighing several sources")
    if primary == "debugging" and ("```" in text or tokens > 150):
        floor("moderate", "debugging requires reading supplied code or logs")
    if primary == "data_analysis" and (("\n" in text and tokens > 60) or "```" in text):
        floor("moderate", "analysis over supplied data")
    if primary == "planning" and (_rx(r"\b\d+[- ](?:day|week|month)s?\b").search(text) or enum_items >= 3):
        floor("moderate", "a multi-period plan has several dependent parts")
    if primary == "writing" and constraints >= 0.3 and len(text.split()) >= 8:
        floor("moderate", "a formal writing task with explicit constraints")
    if primary == "coding" and "```" in text and verbs >= 2:
        floor("moderate", "a change request over supplied code")
    return ComplexityAssessment(
        score=score, category=cat, components={k: round(v, 3) for k, v in comps.items()}, weights=dict(COMPLEXITY_WEIGHTS), adjustments=adjustments,
        methodology="Weighted sum of twelve bounded features (sub-tasks, constraints, reasoning depth, technical depth, context size, intent breadth, output demand, "
                    "structured output, stated difficulty, required precision, domain specificity, consequence of error). Bands: <0.15 simple, <0.30 moderate, <0.48 complex. "
                    "Explicit floor rules (listed under adjustments) can raise a band for short but demanding requests. Ambiguity is excluded. "
                    "Heuristic indicator; not validated against measured difficulty.")


def assess_risk(text: str) -> RiskAssessment:
    inds: List[RiskIndicator] = []
    creds = 0
    for rx, _kind in _SECRET_RXS:
        creds += len(rx.findall(text))
    if creds:
        inds.append(RiskIndicator(category="credentials", level="high", count=creds, note="Possible credentials or secrets"))
    pii_high = len(_SSN_RX.findall(text)) + len(_AADHAAR_RX.findall(text))
    for m in _CARD_RX.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn(digits):
            pii_high += 1
    if pii_high:
        inds.append(RiskIndicator(category="government_or_payment_identifiers", level="high", count=pii_high, note="Possible identification or card numbers"))
    pii_mod = len(_EMAIL_RX.findall(text)) + len(_PHONE_RX.findall(text))
    if pii_mod:
        inds.append(RiskIndicator(category="personal_contact_data", level="moderate", count=pii_mod, note="Email addresses or phone numbers"))
    for cat, rx, note in (("financial", _FIN_RX, "Financial subject matter"), ("medical", _MED_RX, "Health-related subject matter"),
                          ("legal", _LEGAL_RX, "Legal subject matter"), ("security", _SECURITY_RX, "Security-sensitive subject matter"),
                          ("confidential_marking", _CONFIDENTIAL_RX, "Content marked confidential or private")):
        n = len(rx.findall(text))
        if n:
            inds.append(RiskIndicator(category=cat, level="moderate", count=n, note=note))
    vals = {"high": 0.9, "moderate": 0.55, "low": 0.25}
    score = 0.0
    if inds:
        score = min(1.0, max(vals[i.level] for i in inds) + 0.05 * (len(inds) - 1))
    sens = "none" if not inds else ("high" if any(i.level == "high" for i in inds) else "moderate")
    return RiskAssessment(
        sensitivity=sens, score=round(score, 3), indicators=inds, contains_credentials=creds > 0,
        recommends_strict_privacy=sens in {"high"} or any(i.category == "confidential_marking" for i in inds),
        execution_blocked=creds > 0,
        execution_block_reason="Credentials or secrets appear to be present in the prompt; remove them before running a model." if creds else None)


def _expected_output_tokens(intent: str, complexity_hint: float, explicit: List[Requirement]) -> Tuple[int, str]:
    for r in explicit:
        m = re.match(r"(?:max )?(\d+) (words|sentences|characters|tokens|bullets|lines|paragraphs|slides)", r.value)
        if m and r.kind in {"length_limit", "length_target"}:
            n, unit = int(m.group(1)), m.group(2)
            per = {"words": 1.4, "sentences": 28, "characters": 0.25, "tokens": 1, "bullets": 25, "lines": 14, "paragraphs": 120, "slides": 90}[unit]
            return max(16, int(n * per)), f"explicit_{unit}_limit"
    base = {"qa": 250, "reasoning": 600, "math": 500, "coding": 700, "debugging": 600, "architecture": 900, "writing": 600, "creative": 700,
            "editing": 400, "summarization": 300, "translation": 400, "data_analysis": 700, "research": 900, "extraction": 300,
            "planning": 700, "classification": 120, "education": 700}.get(intent, 400)
    return min(4000, int(base * (1 + complexity_hint))), "default_by_intent_and_complexity"


# ── public API ───────────────────────────────────────────────────────────────

def analyze(query: str, task_type_hint: Optional[str] = None) -> QueryProfileV2:
    from app.services.query_hints import TASK_TYPE_HINTS  # local import: avoids cycle with legacy shim
    if not isinstance(query, str) or not query.strip():
        raise ValueError("A non-empty query is required for analysis.")
    if len(query) > MAX_QUERY_CHARS:
        raise ValueError("Query exceeds the 50,000-character analysis limit.")
    text = query.strip()
    has_block = "```" in text or bool(re.search(r"(?m)^\s*>", text)) or len(text.split("\n")) > 6 or len(text.split()) > 60
    words = len(text.split())

    intents, intent_conf = _classify_intents(text)
    hint_applied: Optional[str] = None
    if task_type_hint:
        hint = task_type_hint.strip().lower()
        if hint not in TASK_TYPE_HINTS:
            raise ValueError(f"Unsupported task category: {task_type_hint}")
        forced = TASK_TYPE_TO_INTENT.get(hint, "qa")
        rest = [i for i in intents if i.name != forced]
        intents = [Intent(name=forced, score=1.0, registry_tags=list(INTENT_TAGS[forced]))] + rest[:3]
        hint_applied, intent_conf = hint, 0.95
    primary = intents[0].name
    domain, dom_conf = _classify_domain(text)
    in_tokens, tok_method, exact = estimate_tokens(text)
    explicit, inferred, structured = _extract_requirements(text, in_tokens)
    cx_hint = min(1.0, words / 200.0)
    out_tokens, out_basis = _expected_output_tokens(primary, cx_hint, explicit)
    risk = assess_risk(text)
    complexity = _assess_complexity(text, intents, in_tokens, out_tokens, structured, domain, risk.score)
    out_tokens, out_basis = _expected_output_tokens(primary, complexity.score, explicit)
    ambiguities = _detect_ambiguities(text, words, has_block, intents, explicit)
    from app.services.routing_engine import audience as audience_mod
    aud = audience_mod.assess(text)
    if aud.ambiguous:
        ambiguities.append(Ambiguity(kind="intent_category", severity="major",
                                     message="It is unclear whether you want an AI assistant to use directly or a model/API to integrate into a project. "
                                             "Conversational AI models are shown; Developer & API models are not mixed in.",
                                     clarifying_question=aud.clarifying_question))

    caps: List[str] = []
    modalities = ["text"]
    for it in intents:
        if it.name in GENERATION_REQUIREMENTS:
            c, m = GENERATION_REQUIREMENTS[it.name]
            caps += [x for x in c if x not in caps]
            modalities = list(m)
        elif it.name == "image_analysis":
            modalities = ["text", "image"]
        elif it.name == "audio_transcription":
            modalities = ["audio"]
    if "embedding" in aud.required_model_types and "embedding" not in caps:
        caps.append("embedding")
    if aud.kind == "developer" and any(i.name in {"coding", "debugging", "architecture"} for i in intents) and "coding" not in caps:
        caps.append("coding")
    if complexity.category == "simple" and primary == "math":
        reasoning_req = "light"          # arithmetic or a one-step problem does not need a reasoning model
    elif primary in {"math", "debugging", "architecture"} or complexity.category == "highly_complex":
        reasoning_req = "deep"
    elif complexity.category == "complex" or primary in {"reasoning", "data_analysis", "research"}:
        reasoning_req = "moderate"
    elif complexity.category == "simple" and primary in {"qa", "classification", "extraction", "translation", "editing"}:
        reasoning_req = "none"
    else:
        reasoning_req = "light"
    if any(r.kind == "external_information" for r in inferred):
        pass

    notes: List[str] = []
    if intent_conf < 0.4:
        notes.append("No strong task signal; defaulted to a general question.")
    if len(intents) > 1:
        notes.append("Several task signals were detected; the strongest is primary.")
    if tok_method.startswith("heuristic"):
        notes.append("Token counts are estimates (characters ÷ 4), not exact tokenizer output.")
    task_tags = list(INTENT_TAGS[primary])
    if complexity.category == "simple" and primary in {"math", "reasoning", "coding"}:
        # A one-step arithmetic, explanation or short-program request (a loop, a small function) is within any capable general model's
        # ability; do not demand a specialist tag. Anything with tests, constraints, concurrency or other difficulty markers is raised out of
        # "simple" by the complexity floors and keeps the specialist requirement.
        task_tags += [t for t in ("qa", "general") if t not in task_tags]
        notes_extra = "Simple task: general-purpose models are accepted as a task fit as well as specialists."
    else:
        notes_extra = ""
    return QueryProfileV2(
        original_query=query, primary_intent=primary, secondary_intents=intents[1:], intents=intents,
        task_type=INTENT_TASK_TYPE[primary], task_tags=task_tags, domain=domain, domain_confidence=dom_conf,
        complexity=complexity, required_capabilities=caps, required_modalities=modalities,
        tokens=TokenEstimate(input_tokens=in_tokens, output_tokens=out_tokens, method=tok_method, exact=exact, output_basis=out_basis),
        reasoning_requirement=reasoning_req, structured_output=structured, explicit_requirements=explicit,
        inferred_requirements=inferred, ambiguities=ambiguities, needs_clarification=any(a.severity == "major" for a in ambiguities),
        risk=risk, audience=aud, confidence={"intent": intent_conf, "domain": dom_conf}, user_hint_applied=hint_applied, notes=notes + ([notes_extra] if notes_extra else []))
