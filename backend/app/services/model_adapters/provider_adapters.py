"""
Real LLM Provider Adapters.
Raises ProviderUnavailableError with a clear message if the API key is missing
or the provider call fails. Never falls back to fake output.
"""
import time
from openai import OpenAI, APIError as OpenAIError
import anthropic as anthropic_sdk
from app.services.model_adapters.base import BaseModelAdapter
from app.schemas.model import ModelMetadata
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ProviderUnavailableError(Exception):
    """Raised when a provider cannot be reached or is not configured."""


class OpenAIAdapter(BaseModelAdapter):
    def __init__(self, model: ModelMetadata):
        super().__init__(model)
        if not settings.OPENAI_API_KEY:
            raise ProviderUnavailableError(
                f"OPENAI_API_KEY is not configured. Cannot use model '{model.model_id}'."
            )
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def generate(self, query: str, max_tokens: int = 1024) -> str:
        model_name = self.model.model_id
        t0 = time.time()
        try:
            resp = self._client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": query}],
                max_tokens=max_tokens,
                temperature=0.7,
            )
        except OpenAIError as e:
            raise ProviderUnavailableError(f"OpenAI API error for '{model_name}': {e}")
        self._last_latency = time.time() - t0
        usage = resp.usage
        self._last_input_tokens = usage.prompt_tokens if usage else 0
        self._last_output_tokens = usage.completion_tokens if usage else 0
        return resp.choices[0].message.content or ""



class AnthropicAdapter(BaseModelAdapter):
    def __init__(self, model: ModelMetadata):
        super().__init__(model)
        if not settings.ANTHROPIC_API_KEY:
            raise ProviderUnavailableError(
                f"ANTHROPIC_API_KEY is not configured. Cannot use model '{model.model_id}'."
            )
        self._client = anthropic_sdk.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def generate(self, query: str, max_tokens: int = 1024) -> str:
        model_name = self.model.model_id
        t0 = time.time()
        try:
            msg = self._client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": query}],
            )
        except Exception as e:
            raise ProviderUnavailableError(f"Anthropic API error for '{model_name}': {e}")
        self._last_latency = time.time() - t0
        usage = msg.usage
        self._last_input_tokens = usage.input_tokens if usage else 0
        self._last_output_tokens = usage.output_tokens if usage else 0
        return msg.content[0].text if msg.content else ""


class GeminiAdapter(BaseModelAdapter):
    """Google GenAI SDK adapter for real Gemini API calls."""
    def __init__(self, model: ModelMetadata):
        super().__init__(model)
        if not settings.GEMINI_API_KEY:
            raise ProviderUnavailableError(
                f"GEMINI_API_KEY is not configured. Cannot use model '{model.model_id}'."
            )
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as exc:
            raise ProviderUnavailableError(
                "Google GenAI SDK is unavailable. Activate the project virtual environment "
                "and install dependencies with `python -m pip install -r requirements.txt`."
            ) from exc
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._types = genai_types

    def generate(self, query: str, max_tokens: int = 1024) -> str:
        t0 = time.time()
        try:
            response = self._client.models.generate_content(
                model=self.model.model_id,
                contents=query,
                config=self._types.GenerateContentConfig(
                    max_output_tokens=max_tokens, temperature=0.7,
                ),
            )
        except Exception as exc:
            raise ProviderUnavailableError(
                f"Gemini API error for '{self.model.model_id}': {exc}"
            ) from exc
        self._last_latency = time.time() - t0
        usage = getattr(response, "usage_metadata", None)
        self._last_input_tokens = getattr(usage, "prompt_token_count", None)
        self._last_output_tokens = getattr(usage, "candidates_token_count", None)
        return getattr(response, "text", "") or ""


class GroqAdapter(BaseModelAdapter):
    """Groq adapter using Groq's OpenAI-compatible inference endpoint."""
    def __init__(self, model: ModelMetadata):
        super().__init__(model)
        if not settings.GROQ_API_KEY:
            raise ProviderUnavailableError(
                f"GROQ_API_KEY is not configured. Cannot use model '{model.model_id}'."
            )
        self._client = OpenAI(api_key=settings.GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

    def generate(self, query: str, max_tokens: int = 1024) -> str:
        t0 = time.time()
        try:
            response = self._client.chat.completions.create(
                model=self.model.model_id,
                messages=[{"role": "user", "content": query}],
                max_tokens=max_tokens,
                temperature=0.7,
            )
        except OpenAIError as exc:
            raise ProviderUnavailableError(f"Groq API error for '{self.model.model_id}': {exc}") from exc
        self._last_latency = time.time() - t0
        usage = response.usage
        self._last_input_tokens = usage.prompt_tokens if usage else None
        self._last_output_tokens = usage.completion_tokens if usage else None
        return response.choices[0].message.content or ""

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        # Current published Groq pricing for GPT-OSS models, USD per million tokens.
        prices = {
            "openai/gpt-oss-20b": (0.075, 0.30),
            "openai/gpt-oss-120b": (0.15, 0.60),
        }
        input_price, output_price = prices.get(self.model.model_id, (0.0, 0.0))
        return input_tokens * input_price / 1_000_000 + output_tokens * output_price / 1_000_000


class OpenRouterAdapter(BaseModelAdapter):
    """OpenRouter adapter using its OpenAI-compatible chat completions endpoint.

    AI Compass selects the specific model_id first; this adapter only
    executes that model via OpenRouter. Model selection is never delegated
    to OpenRouter.
    """
    _BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, model: ModelMetadata):
        super().__init__(model)
        if not settings.OPENROUTER_API_KEY:
            raise ProviderUnavailableError(
                f"OPENROUTER_API_KEY is not configured. Cannot use model '{model.model_id}'."
            )
        self._client = OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=self._BASE_URL,
        )

    def generate(self, query: str, max_tokens: int = 1024) -> str:
        t0 = time.time()
        try:
            response = self._client.chat.completions.create(
                model=self.model.model_id,
                messages=[{"role": "user", "content": query}],
                max_tokens=max_tokens,
                temperature=0.7,
            )
        except OpenAIError as exc:
            raise ProviderUnavailableError(
                f"OpenRouter API error for '{self.model.model_id}': {exc}"
            ) from exc
        self._last_latency = time.time() - t0
        usage = response.usage
        self._last_input_tokens = usage.prompt_tokens if usage else None
        self._last_output_tokens = usage.completion_tokens if usage else None
        return response.choices[0].message.content or ""

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        # Free-tier endpoints report $0 pricing; cost_per_1k_tokens in the
        # registry reflects the actual OpenRouter published rate.
        return (input_tokens + output_tokens) / 1000 * self.model.cost_per_1k_tokens
