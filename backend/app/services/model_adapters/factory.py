"""
Adapter factory.
Returns the correct real provider adapter.
Raises ProviderUnavailableError — never falls back to fake output.
"""
from app.schemas.model import ModelMetadata
from app.core.config import settings
from app.core.logging import get_logger
from app.services.model_adapters.provider_adapters import ProviderUnavailableError

logger = get_logger(__name__)


def get_adapter(model: ModelMetadata):
    provider = model.provider.lower()

    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise ProviderUnavailableError(
                f"OPENAI_API_KEY is not set. Model '{model.model_id}' is unavailable."
            )
        from app.services.model_adapters.provider_adapters import OpenAIAdapter
        return OpenAIAdapter(model)

    if provider == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            raise ProviderUnavailableError(
                f"ANTHROPIC_API_KEY is not set. Model '{model.model_id}' is unavailable."
            )
        from app.services.model_adapters.provider_adapters import AnthropicAdapter
        return AnthropicAdapter(model)

    if provider == "google":
        if not settings.GEMINI_API_KEY:
            raise ProviderUnavailableError(
                f"GEMINI_API_KEY is not set. Model '{model.model_id}' is unavailable."
            )
        from app.services.model_adapters.provider_adapters import GeminiAdapter
        return GeminiAdapter(model)

    if provider == "groq":
        if not settings.GROQ_API_KEY:
            raise ProviderUnavailableError(
                f"GROQ_API_KEY is not set. Model '{model.model_id}' is unavailable."
            )
        from app.services.model_adapters.provider_adapters import GroqAdapter
        return GroqAdapter(model)

    if provider == "openrouter":
        if not settings.OPENROUTER_API_KEY:
            raise ProviderUnavailableError(
                f"OPENROUTER_API_KEY is not set. Model '{model.model_id}' is unavailable."
            )
        from app.services.model_adapters.provider_adapters import OpenRouterAdapter
        return OpenRouterAdapter(model)

    raise ProviderUnavailableError(
        f"No adapter configured for provider '{model.provider}' (model: '{model.model_id}'). "
        f"Add the required API key to your .env file."
    )
