"""Task-aware local prompt optimizer.

This service uses the same deterministic query analysis as routing and does
not require or call an external model provider.
"""
from dataclasses import dataclass
import re

from app.schemas.query import QueryProfile


@dataclass(frozen=True)
class OptimizationResult:
    prompt: str
    task_type: str
    domain: str
    method: str = "Task-aware local optimizer"


_TASK_GUIDANCE: dict[str, tuple[str, ...]] = {
    "research": (
        "Frame the research question and keep the scope tied to the task.",
        "Identify relevant evidence and distinguish established information from interpretation; use citations only when sources are available or requested.",
        "Synthesize the findings and state material evidence gaps rather than filling them with assumptions.",
    ),
    "coding": (
        "Extract the implementation requirements and use the environment, language, and constraints stated in the task.",
        "Address relevant edge cases; state only assumptions needed to proceed when details are missing.",
        "Provide the implementation, a concise explanation, and focused tests or verification steps without adding unrelated dependencies or behavior.",
    ),
    "creative": (
        "Preserve the requested subject, purpose, audience, tone, and format wherever they are stated.",
        "Make the requested piece coherent and ready to use; avoid adding an unrelated theme, premise, or commentary.",
        "Keep length and structure proportional to the requested format.",
    ),
    "analysis": (
        "Identify the factors or variables relevant to the question and explain how they relate.",
        "Present the analytical approach and findings, distinguishing evidence from interpretation and noting important limitations.",
        "Explain the implications that follow from the findings without overstating causality.",
    ),
    "math": (
        "Set up the problem and show the method and intermediate steps needed to verify the result.",
        "Define variables and state assumptions where useful; check that the final result answers the original question.",
        "End with the result clearly identified and keep the explanation proportional to the problem.",
    ),
    "reasoning": (
        "Break the question into the parts needed to reach a well-supported answer.",
        "Explain the relevant reasoning and distinguish assumptions from conclusions.",
        "End with a direct conclusion that answers the original question.",
    ),
    "summarization": (
        "Identify the main points and supporting details relevant to the requested subject.",
        "If source material is provided, stay grounded in it; otherwise use reliable established information and make uncertainty clear.",
        "Organize the response as a concise overview, key points, and synthesis; separate causes, responses, or outcomes when relevant to the request.",
    ),
    "presentation": (
        "Build a clear narrative for the requested topic and audience, using only audience details stated in the task.",
        "Provide a logical slide-by-slide structure with a title, one main idea, and concise supporting points for each slide.",
        "Suggest visuals only where they help communicate the content; do not invent facts or data.",
    ),
    "image-generation": (
        "Preserve the requested subject and any composition, style, lighting, or medium specified in the task.",
        "Clarify visual hierarchy and important details without introducing unrelated objects or unsupported text.",
        "Return a concise, ready-to-paste image prompt rather than commentary.",
    ),
    "video-generation": (
        "Preserve the requested subject, purpose, style, and duration if specified.",
        "Describe the sequence of visible events and relevant camera or motion direction only where it supports the task.",
        "Return coherent, ready-to-paste direction for a video-generation tool.",
    ),
    "audio-generation": (
        "Preserve the requested audio purpose, mood, style, and any instrumentation or voice details stated in the task.",
        "Describe progression and sonic details only where they are relevant to the requested result.",
        "Return concise, ready-to-paste direction for an audio-generation tool.",
    ),
    "qa": (
        "Answer the request directly and organize the response around its distinct parts when useful.",
        "Use clear, specific language and add only context needed to answer the request.",
        "Do not assume requirements or facts that are not stated; make material uncertainty explicit.",
    ),
    "education": (
        "Explain the requested topic in a clear progression, starting with the concepts needed to understand it.",
        "Use relevant examples to make difficult ideas concrete, and define terminology when it first appears.",
        "End with a brief recap of the main ideas without introducing unrelated material.",
    ),
    "music-generation": (
        "Preserve the requested musical purpose, mood, style, and any instrumentation or voice details stated in the task.",
        "Describe progression and sonic details only where they are relevant to the requested result.",
        "Keep the direction concise and ready to use in an audio-generation tool.",
    ),
    "design": (
        "Preserve the requested design purpose, subject, and any visual direction stated in the task.",
        "Clarify the intended hierarchy and important details without introducing unrelated elements.",
        "Keep the result suitable for direct use in the requested design workflow.",
    ),
    "debugging": (
        "Use the supplied code, error, and environment as the source of truth; do not assume missing implementation details.",
        "Identify the likely cause, propose the smallest relevant correction, and explain any important trade-offs.",
        "Include focused steps to verify the fix and mention relevant edge cases.",
    ),
}


def _output_structure(task_type: str, query: str) -> list[str]:
    text = query.lower()
    if task_type == "research":
        return ["Research question and scope", "Findings grouped by theme", "Evidence and limitations", "Synthesis"]
    if task_type == "coding":
        return ["Requirements and assumptions", "Implementation", "Relevant edge cases", "Focused tests"]
    if task_type == "creative":
        return ["Finished requested piece", "Brief supporting notes only if they improve usability"]
    if task_type == "analysis":
        return ["Question and scope", "Findings and supporting analysis", "Interpretation and implications", "Limitations"]
    if task_type == "math":
        return ["Setup and method", "Worked steps", "Final result and check"]
    if task_type == "education":
        return ["Core concept", "Progressive explanation", "Examples", "Brief recap"]
    if task_type == "presentation":
        return ["Slide-by-slide outline", "Key message and supporting points per slide", "Visual direction where useful"]
    if task_type == "image-generation":
        return ["One concise, ready-to-paste image prompt"]
    if task_type == "video-generation":
        return ["Scene or event sequence", "Motion and camera direction where relevant", "Ready-to-paste generation prompt"]
    if task_type in {"audio-generation", "music-generation"}:
        return ["Audio purpose and style", "Progression and sound details", "Ready-to-paste generation prompt"]
    if task_type == "summarization":
        sections = ["Overview"]
        has_causes = bool(re.search(r"\b(cause|causes|contributing factors|drivers)\b", text))
        has_responses = bool(re.search(r"\b(response|responses|policy|policies|intervention|interventions)\b", text))
        if has_causes:
            sections.append("Causes or contributing factors")
        if has_responses:
            sections.append("Responses or interventions")
        if has_causes or has_responses or re.search(r"\b(effect|effects|consequences|outcomes|limitations)\b", text):
            sections.append("Consequences, effectiveness, or limitations where relevant")
        sections.append("Key points and synthesis")
        return sections
    return ["Direct answer", "Supporting explanation where useful"]


def optimize(query: str, profile: QueryProfile) -> OptimizationResult:
    """Return a structured prompt that preserves the user's request verbatim."""
    task_type = profile.task_type.lower()
    guidance = _TASK_GUIDANCE.get(task_type, _TASK_GUIDANCE["qa"])
    short_query = len(query) < 280
    selected_guidance = guidance if short_query else guidance[:2]

    output_structure = _output_structure(task_type, query)
    if not short_query:
        output_structure = output_structure[:3]
    formatted_structure = "\n".join(
        f"{index}. {section}" for index, section in enumerate(output_structure, start=1)
    )

    prompt = (
        f"## Task\n{query.strip()}\n\n"
        "## Approach\n"
        + "\n".join(f"- {instruction}" for instruction in selected_guidance)
        + "\n\n## Suggested response structure\n"
        + formatted_structure
        + "\n\nPreserve the task's stated requirements and do not invent facts, sources, or constraints."
    )
    return OptimizationResult(
        prompt=prompt,
        task_type=profile.task_type,
        domain=profile.domain,
    )
