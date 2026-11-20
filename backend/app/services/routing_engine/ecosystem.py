"""Category-first routing for the approved ecosystem.

Stage order: (1) resolve ONE category from the query, (2) keep only products that serve it, (3) score only those.
A product is never compared with products from another category, and no credential is consulted anywhere here.

Resolution is deterministic: each category has weighted word-boundary patterns; the category with the highest score wins.
Ties break by ``CATEGORY_PRIORITY`` (specific artefact categories before generic chat). Every fired signal is reported,
so a recommendation can always be traced back to the words that caused it. No signal at all means ``conversational``.
"""
import re
from typing import Dict, List, Optional, Set, Tuple

from app.data.approved_ecosystem import CATEGORIES, CATEGORY_LABELS, CATEGORY_PRIORITY
from app.schemas.model import ModelMetadata
from app.services.routing_engine.types import CategoryResolution


def _rx(p: str):
    return re.compile(p, re.IGNORECASE)


_GEN = r"(?:generate|create|make|draw|design|render|paint|illustrate|produce|compose|animate|build|write|need|want)"

# (signal name, pattern, weight)
_RULES: Dict[str, List[Tuple[str, "re.Pattern", float]]] = {
    "image": [
        ("generate_image", _rx(r"\b" + _GEN + r"\b[^.?!\n]{0,40}\b(?:image|picture|illustration|logo|poster|photo|icon|artwork|portrait|wallpaper|banner|avatar|sticker|thumbnail)s?\b"), 3.0),
        ("text_to_image", _rx(r"\btext[- ]to[- ]image\b|\bimage generat\w+|\bai (?:art|image)s?\b"), 3.0),
        ("image_noun_phrase", _rx(r"\b(?:image|picture|illustration|artwork|render|wallpaper|logo|photo)s?\s+of\b"), 2.0),
        ("art_style", _rx(r"\b(?:photo-?realistic|photorealistic|anime|watercolou?r|oil painting|concept art|digital art|cartoon|3d render|vector art)\b"), 1.5),
        ("image_editing", _rx(r"\b(?:remove|replace|change|edit|retouch|upscale|extend)\b[^.?!\n]{0,30}\b(?:background|photo|image|picture)\b"), 1.8),
    ],
    "video": [
        ("generate_video", _rx(r"\b" + _GEN + r"\b[^.?!\n]{0,40}\b(?:video|film|clip|animation|animated|reel|short|trailer|footage)s?\b"), 3.5),
        ("text_to_video", _rx(r"\b(?:text|image)[- ]to[- ]video\b|\bvideo generat\w+|\bai video\b"), 3.5),
        ("video_noun_phrase", _rx(r"\b(?:cinematic|b-?roll|camera (?:pan|move\w*)|drone shot|tracking shot|slow[- ]motion)\b"), 1.6),
        ("video_of", _rx(r"\bvideos?\s+of\b"), 2.0),
    ],
    "music_voice": [
        ("generate_music", _rx(r"\b" + _GEN + r"\b[^.?!\n]{0,40}\b(?:music|song|soundtrack|melody|beat|jingle|instrumental|track|lo-?fi)\b"), 3.5),
        ("music_generation", _rx(r"\bmusic generat\w+|\bai music\b|\btext[- ]to[- ]music\b|\bsong (?:with|from) (?:lyrics|vocals)\b"), 3.5),
        ("voice_tts", _rx(r"\b(?:text[- ]to[- ]speech|tts|voice[- ]?over|narrat\w+|voice clon\w+|clone (?:my |a )?voice|dubb\w+|lip[- ]?sync|synthetic voice|ai voice|speech synthesis)\b"), 3.5),
        ("to_speech", _rx(r"\b(?:convert|turn|read|speak|say)\b[^.?!\n]{0,40}\b(?:to|into|aloud as)\s+(?:speech|audio|a voice|natural voice|spoken)\b|\b(?:natural|human[- ]like|realistic)[- ]?(?:sounding )?voice\b"), 3.5),
        ("voice_agent", _rx(r"\b(?:voice agents?|real-?time voice|voice assistants?|conversational voice|speech[- ]to[- ]speech|speech recognition|transcri\w+|speech[- ]to[- ]text)\b"), 3.0),
        ("audio_words", _rx(r"\b(?:podcast|audiobook|sound effects?|sfx|vocals?|singer|hindi voice|regional voice)\b"), 1.5),
    ],
    "document_design": [
        ("slides", _rx(r"\b(?:presentation|slide deck|slides|powerpoint|pitch deck|keynote|deck)\b"), 3.5),
        ("ui_design", _rx(r"\b(?:ui|ux|wireframes?|mock-?ups?|prototype|design system|figma|user interface|app screens?|landing page|web ?site|portfolio site)\b"), 2.6),
        ("graphic_design", _rx(r"\b(?:poster|flyer|brochure|infographic|social media (?:post|graphic)s?|brand kit|business card|menu design|resume template|canva)\b"), 2.6),
        ("brand_social", _rx(r"\b(?:brand kit|brand colou?rs|template|instagram|social media|linkedin|facebook|story (?:post|graphic)|canva)\b"), 2.0),
        ("document_build", _rx(r"\b" + _GEN + r"\b[^.?!\n]{0,30}\b(?:document|doc|report|one-?pager|whitepaper|ebook|newsletter template)\b"), 1.6),
        ("no_code_app", _rx(r"\b(?:no-?code|low-?code|app builder|build (?:me )?a (?:web ?site|web app|landing page)|prototype (?:an? )?app)\b"), 2.4),
    ],
    "coding": [
        ("code_words", _rx(r"\b(?:code|coding|function|class|method|(?:python|bash|shell|node|js|sql) script|programm?(?:ing|er)?|algorithm|endpoint|sql|regex|python|javascript|typescript|java|c\+\+|c#|rust|golang|react|node\.?js|django|flask|fastapi|docker|kubernetes|unit tests?|refactor\w*|compile\w*|repo(?:sitory)?|pull requests?|commit|git|bugs?|debug\w*|stack ?trace|exception|segfault|lint\w*)\b"), 1.6),
        ("coding_assistant", _rx(r"\b(?:autocomplete|code completion|ide|vs ?code|jetbrains|copilot|cursor|pair programm\w+|code review|coding (?:assistant|agent|tool)|codebase|terminal agent|agentic coding)\b"), 3.0),
        ("write_code", _rx(r"\b(?:write|implement|fix|debug|refactor|review|optimi[sz]e|port|migrate|test)\b[^.?!\n]{0,40}\b(?:code|function|class|script|program|bug|api|module|query|component|codebase)\b"), 2.6),
        ("code_block", _rx(r"```"), 2.0),
    ],
    "api_models": [
        ("api_access", _rx(r"\b(?:llm apis?|model apis?|inference apis?|api keys?|(?:free|cheap|open) (?:\w+\s+){0,2}apis?|through an api|via (?:an? )?api|apis? for (?:models|llms))\b"), 3.5),
        ("inference_platform", _rx(r"\b(?:groq|openrouter|hugging ?face|ai21|together ai|fireworks|replicate|inference providers?|model hub|model router|inference)\b"), 3.5),
        ("open_weights", _rx(r"\b(?:open[- ]weights?|open[- ]source (?:models?|llms?)|self[- ]host\w*|run (?:it |them |models? )?locally|on[- ]prem\w*|fine[- ]?tun\w+)\b"), 3.0),
        ("integrate_model", _rx(r"\b(?:integrat\w+|plug (?:it )?into|embed (?:it )?(?:in|into)|sdk)\b[^.?!\n]{0,40}\b(?:model|llm|ai)\b|\b(?:model|llm)s?\b[^.?!\n]{0,40}\b(?:integrat\w+|sdk|into my app|for my app|in my app)\b"), 3.0),
        ("unified_api", _rx(r"\b(?:one|single|unified|common)\s+api\b[^.?!\n]{0,40}\b(?:models?|llms?|providers?)\b|\bswitch(?:ing)? between\b[^.?!\n]{0,20}\b(?:models?|providers?|llms?)\b|\bmany (?:models|providers) (?:through|via|with) one\b"), 3.5),
        ("embeddings_rag", _rx(r"\b(?:embeddings?|vector (?:search|database|store)|rerank\w*|rag pipeline|retrieval[- ]augmented)\b"), 2.4),
        ("model_for_project", _rx(r"\b(?:which|what|suggest|recommend|best)\b[^.?!\n]{0,30}\b(?:models?|llms?)\b[^.?!\n]{0,40}\b(?:for (?:my|our) (?:project|app|product|startup|chatbot|agent)|to build|to integrate)\b"), 3.0),
    ],
    "conversational": [
        ("question", _rx(r"^\s*(?:please\s+)?(?:explain|summari[sz]e|translate|what|why|how|who|when|where|which|tell me|help me|solve|calculate|compare|define|describe|is |are |can |could |should |do |does )"), 1.2),
        ("writing", _rx(r"\b(?:write|draft|compose|rewrite|proofread|edit)\b[^.?!\n]{0,30}\b(?:email|e-mail|letter|essay|story|poem|speech|summary|message|blog|article|cover letter)\b"), 2.0),
        ("research_chat", _rx(r"\b(?:research|latest news|current events|fact[- ]check|with sources|with citations|cite sources|web search|look up)\b"), 1.4),
        ("reasoning", _rx(r"\b(?:reason|think through|pros and cons|brainstorm|advice|opinion|analy[sz]e|study plan|explain like)\b"), 1.2),
    ],
}

# Sub-capabilities that must be present on the model (hard requirement) when the query states them.
_SUBTYPE_RULES: Dict[str, List[Tuple[str, "re.Pattern", Tuple[str, ...]]]] = {
    "music_voice": [
        ("music", _rx(r"\b(?:music|song|soundtrack|melody|beat|jingle|instrumental|lo-?fi|lyrics? to song|singer|vocals?)\b"), ("music",)),
        ("voice", _rx(r"\b(?:text[- ]to[- ]speech|tts|voice[- ]?over|narrat\w+|voice clon\w+|dubb\w+|synthetic voice|ai voice|voice agents?|speech[- ]to[- ]speech|real-?time voice|speech synthesis|audiobook|transcri\w+|speech[- ]to[- ]text|speech recognition|to speech|natural voice)\b"), ("voice", "transcription")),
    ],
}

# Feature vocabulary: query pattern -> strength tags that satisfy it (matched against ModelMetadata.strengths).
FEATURES: List[Tuple[str, "re.Pattern", Tuple[str, ...]]] = [
    ("photorealistic", _rx(r"\b(?:photo-?realistic|realistic|lifelike|hyper-?real\w*)\b"), ("photorealism", "realism")),
    ("artistic_style", _rx(r"\b(?:artistic|stylised|stylized|painterly|illustrat\w+|concept art|aesthetic|fantasy art|anime)\b"), ("artistic", "stylised", "illustration", "concept-art", "aesthetic")),
    ("text_in_image", _rx(r"\b(?:text (?:in|on|inside) (?:the )?image|readable text|typography|lettering|logo with text|poster with text)\b"), ("text-rendering", "text-effects")),
    ("commercial_safe", _rx(r"\b(?:commercial(?:ly)?(?: use| safe)?|copyright[- ]safe|brand[- ]safe|licensed|ip[- ]safe)\b"), ("commercially-safe",)),
    ("image_edit", _rx(r"\b(?:edit(?:ing)?|retouch|inpaint\w*|remove (?:the )?background|replace|modify (?:an? )?(?:image|photo))\b"), ("image-editing", "multi-image-blend")),
    ("vector", _rx(r"\b(?:vector|svg|scalable)\b"), ("vector",)),
    ("api_needed", _rx(r"\b(?:api|programmatic\w*|sdk|integrat\w+)\b"), ("api-access", "inference-api", "unified-api")),
    ("open_weights", _rx(r"\b(?:open[- ]weights?|open[- ]source|self[- ]host\w*|run locally)\b"), ("open-weights", "self-host")),
    ("cinematic", _rx(r"\b(?:cinematic|film(?:ic)?|movie|trailer|dramatic)\b"), ("cinematic", "film-production")),
    ("image_to_video", _rx(r"\b(?:image[- ]to[- ]video|animate (?:an? |my |this |the )?(?:image|photo|picture)|(?:video|clip|animation|movie) (?:from|out of|based on|using) (?:an? |my |this |the |that )?(?:image|photo|picture|still))\b"), ("image-to-video",)),
    ("text_to_speech", _rx(r"\b(?:text[- ]to[- ]speech|tts|speech (?:synthesis|from)|(?:to|into) speech|read (?:aloud|out)|narrat\w+|voice-?over)\b"), ("text-to-speech", "narration")),
    ("camera_control", _rx(r"\b(?:camera (?:control|angles?|moves?|pan)|motion control|tracking shot|dolly)\b"), ("camera-control", "motion-control", "creative-controls")),
    ("native_audio", _rx(r"\b(?:with (?:sound|audio|dialogue)|native audio|sound effects?)\b"), ("native-audio",)),
    ("social_video", _rx(r"\b(?:tiktok|reels?|shorts|(?:social|instagram) (?:media )?videos?)\b"), ("social-video",)),
    ("vocals", _rx(r"\b(?:vocals?|singer|lyrics|sung)\b"), ("vocals", "lyrics-to-song")),
    ("instrumental", _rx(r"\b(?:instrumental|background music|soundtrack|score)\b"), ("instrumental", "soundtrack")),
    ("voice_clone", _rx(r"\b(?:voice clon\w+|clone (?:my |a )?voice|custom voice)\b"), ("voice-cloning",)),
    ("multilingual_voice", _rx(r"\b(?:multilingual|indian languages?|hindi|tamil|marathi|bengali|regional languages?|many languages|dubbing)\b"), ("multilingual", "indian-languages", "dubbing")),
    ("low_latency_voice", _rx(r"\b(?:low[- ]latency|real-?time|live|voice agents?|conversational voice)\b"), ("low-latency", "real-time", "voice-agents", "conversational-voice")),
    ("transcription", _rx(r"\b(?:transcri\w+|speech[- ]to[- ]text)\b"), ("transcription", "speech-to-text")),
    ("slides", _rx(r"\b(?:slides?|presentation|pitch deck|slide deck)\b"), ("slides", "presentation", "pitch-deck")),
    ("ui_design", _rx(r"\b(?:ui|ux|wireframes?|mock-?ups?|interface|design system)\b"), ("ui-design", "wireframe", "mockup", "design-system", "prototype")),
    ("web_app", _rx(r"\b(?:web ?site|web app|landing page|no-?code|prototype)\b"), ("web-app", "landing-page", "website", "no-code", "prototype")),
    ("social_graphic", _rx(r"\b(?:poster|flyer|social media|instagram|brand kit|template)\b"), ("poster", "social-media", "templates", "brand-kit", "flyer")),
    ("collaboration", _rx(r"\b(?:collaborat\w+|team|shared|co-?edit)\b"), ("collaboration",)),
    ("ide", _rx(r"\b(?:ide|vs ?code|jetbrains|editor|autocomplete|inline)\b"), ("ide", "autocomplete")),
    ("agentic", _rx(r"\b(?:agent|agentic|autonomous|multi[- ]step|end[- ]to[- ]end)\b"), ("agent", "autonomous-tasks")),
    ("multi_file", _rx(r"\b(?:multi[- ]file|whole (?:repo|codebase)|entire (?:repo|codebase)|codebase|across files|large refactor)\b"), ("codebase-aware", "multi-file-edit")),
    ("aws", _rx(r"\b(?:aws|amazon web services|lambda|s3|ec2|cloudformation|cdk)\b"), ("aws", "cloud")),
    ("github", _rx(r"\b(?:github|pull requests?|pr review)\b"), ("github", "pull-requests", "code-review")),
    ("code_review", _rx(r"\b(?:code review|review (?:my |this )?(?:pr|code|pull request))\b"), ("code-review",)),
    ("terminal", _rx(r"\b(?:terminal|cli|command line|shell)\b"), ("terminal",)),
    ("debugging", _rx(r"\b(?:debug\w*|bugs?|stack ?trace|fix (?:this|the) (?:error|bug))\b"), ("debugging", "refactor")),
    ("web_search", _rx(r"\b(?:latest|current|today|news|recent|up[- ]to[- ]date|web search|real[- ]time)\b"), ("web-search", "current-events", "real-time")),
    ("citations", _rx(r"\b(?:citations?|cite|sources|references|with sources)\b"), ("citations", "research")),
    ("long_context", _rx(r"\b(?:long (?:document|pdf|report|context)|entire (?:book|document|paper)|hundreds of pages|large (?:document|file)s?)\b"), ("long-context", "document-upload", "file-analysis")),
    ("math", _rx(r"\b(?:math\w*|prove|proof|equation|calculus|algebra|olympiad)\b"), ("math", "reasoning")),
    ("reasoning", _rx(r"\b(?:reasoning|step[- ]by[- ]step|logic\w*|puzzle|analy[sz]e)\b"), ("reasoning", "analysis")),
    ("creative_writing", _rx(r"\b(?:essay|story|poem|blog|article|cover letter|email|rewrite)\b"), ("writing",)),
    ("multimodal_input", _rx(r"\b(?:this (?:image|photo|screenshot|diagram|chart)|upload(?:ed)? (?:an? )?(?:image|photo|file)|video input|audio input)\b"), ("multimodal", "file-analysis")),
    ("workspace", _rx(r"\b(?:google (?:docs|sheets|slides|drive|workspace)|gmail|gdocs)\b"), ("google-workspace", "document-generation")),
    ("fast_inference", _rx(r"\b(?:fast(?:est)?|speed|latency|tokens per second)\b"), ("fast-inference", "low-latency")),
    ("multi_provider", _rx(r"\b(?:multiple (?:providers|models)|switch between models|many models|one api|unified api|fallback)\b"), ("multi-provider", "unified-api", "model-switching", "fallback-routing")),
    ("enterprise", _rx(r"\b(?:enterprise|private deployment|on[- ]prem\w*|vpc|compliance)\b"), ("enterprise", "private-deployment")),
    ("embeddings", _rx(r"\b(?:embeddings?|vector|rerank\w*)\b"), ("embeddings",)),
    ("real_time_social", _rx(r"\b(?:twitter|tweets?|x\.com|trending|social media trends?)\b"), ("social-media", "real-time")),
]


def _score_category(text: str) -> Tuple[Dict[str, float], Dict[str, List[str]]]:
    scores: Dict[str, float] = {c: 0.0 for c in CATEGORIES}
    signals: Dict[str, List[str]] = {c: [] for c in CATEGORIES}
    for cat, rules in _RULES.items():
        for name, rx, weight in rules:
            if rx.search(text):
                scores[cat] += weight
                signals[cat].append(name)
    return scores, signals


def extract_features(text: str) -> List[Dict[str, object]]:
    """Features the query asks for: [{feature, accepts:[strength tags]}]."""
    return [{"feature": name, "accepts": list(tags)} for name, rx, tags in FEATURES if rx.search(text)]


_SATISFIABLE: Dict[str, Set[str]] = {}


def _category_tags(category: str) -> Set[str]:
    """Every strength/capability tag documented by at least one approved product of the category. Static: depends on the approved list, not on
    which products survived filtering, so removing or adding a candidate can never change which features count."""
    if category not in _SATISFIABLE:
        from app.data.approved_ecosystem import approved_models
        tags: Set[str] = set()
        for m in approved_models():
            if serves(m, category):
                tags |= {s.lower() for s in (m.strengths or [])} | {c.lower() for c in (m.capabilities or [])}
        _SATISFIABLE[category] = tags
    return _SATISFIABLE[category]


def split_satisfiable(category: str, features: List[Dict[str, object]]) -> Tuple[List[Dict[str, object]], List[str]]:
    """A requested feature no product of the category documents (e.g. 'multimodal input' in an image-generation category) cannot separate
    anyone; counting it would only lower every product's coverage equally and flatten confidence. Returned separately so it is still disclosed."""
    have = _category_tags(category)
    keep = [f for f in features if have & {str(a).lower() for a in f["accepts"]}]  # type: ignore[union-attr]
    dropped = [str(f["feature"]) for f in features if f not in keep]
    return keep, dropped


def resolve(text: str, hint: Optional[str] = None, *, audience_ambiguous: bool = False) -> CategoryResolution:
    """Pick ONE category. ``hint`` (a UI task-type hint) adds a bounded nudge but can never override explicit query evidence."""
    scores, signals = _score_category(text)
    hint_map = {"coding": "coding", "image-generation": "image", "video-generation": "video", "audio-generation": "music_voice", "music-generation": "music_voice",
                "presentation": "document_design", "design": "document_design", "research": "conversational"}
    hinted = hint_map.get(hint or "")
    if hinted:
        scores[hinted] += 1.5
        signals[hinted].append("user_task_hint")
    ranked = sorted(CATEGORIES, key=lambda c: (-scores[c], CATEGORY_PRIORITY.index(c)))
    top, second = ranked[0], ranked[1]
    top_score, second_score = scores[top], scores[second]
    if top_score <= 0:
        top, top_score = "conversational", 0.0
        reason = "No specialised signal in the query, so the Conversational AI category is used."
        second, second_score = next(c for c in ranked if c != "conversational"), 0.0
    else:
        reason = f"{CATEGORY_LABELS[top]} scored {top_score:.1f} from: {', '.join(signals[top])}."
    # Confidence of the category decision: strength of the winning evidence x margin over the runner-up. 0 = no evidence, 1 = unambiguous.
    strength = min(1.0, top_score / 3.5) if top_score > 0 else 0.35
    margin = (top_score - second_score) / top_score if top_score > 0 else 0.6
    conf = round(max(0.0, min(1.0, 0.6 * strength + 0.4 * margin)), 3)
    ambiguous = top_score > 0 and second_score > 0 and (top_score - second_score) < 0.8
    features, unsatisfiable = split_satisfiable(top, extract_features(text))
    subtype: List[str] = []
    for name, rx, _tags in _SUBTYPE_RULES.get(top, []):
        if rx.search(text):
            subtype.append(name)
    # A query that is both music and voice (rare) does not hard-require either.
    if len(subtype) > 1:
        subtype = []
    return CategoryResolution(
        category=top, label=CATEGORY_LABELS[top], scores={c: round(scores[c], 3) for c in CATEGORIES}, signals=signals[top], confidence=conf,
        runner_up=second if second_score > 0 else None, runner_up_score=round(second_score, 3), ambiguous=ambiguous or audience_ambiguous,
        required_subtype=subtype[0] if subtype else None, features=features, unsatisfiable_features=unsatisfiable, reason=reason)


def serves(model: ModelMetadata, category: str) -> bool:
    return model.ecosystem_category == category or category in (model.secondary_categories or [])


def subtype_ok(model: ModelMetadata, subtype: Optional[str]) -> bool:
    if not subtype:
        return True
    strengths = set(model.strengths or [])
    need = {"music": {"music", "song", "instrumental", "soundtrack"}, "voice": {"voice", "text-to-speech", "transcription", "voice-agents"}}.get(subtype, set())
    return bool(strengths & need)


def feature_coverage(model: ModelMetadata, features: List[Dict[str, object]]) -> Tuple[float, List[str], List[str]]:
    """(coverage 0-1, matched feature names, unmet feature names). With no requested features coverage is None-equivalent 1.0 and nothing is matched."""
    if not features:
        return 1.0, [], []
    have: Set[str] = {s.lower() for s in (model.strengths or [])} | {c.lower() for c in (model.capabilities or [])}
    matched = [str(f["feature"]) for f in features if have & {str(a).lower() for a in f["accepts"]}]  # type: ignore[union-attr]
    unmet = [str(f["feature"]) for f in features if str(f["feature"]) not in matched]
    return round(len(matched) / len(features), 4), matched, unmet
