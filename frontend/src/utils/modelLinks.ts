/**
 * Provider deep links.
 *
 * AI Compass is a routing layer. It does not generate the answer, so
 * the "open the recommended model" action must leave this application
 * entirely and land the user on the provider that actually serves the
 * model. That means the destinations belong here, in one place, rather
 * than being scattered through components.
 *
 * Two rules this file exists to enforce:
 *
 * 1. Only a provider that *officially* documents a way to carry a
 *    prompt in the URL gets `supportsPromptPrefill`. Inventing a query
 *    parameter produces a link that looks right and silently drops the
 *    prompt, which is worse than not offering it at all.
 * 2. When a provider has no supported prefill, callers copy the prompt
 *    and open the plain provider page, then tell the user to paste.
 *
 * The backend registry does not return a URL (`backend/app/schemas/
 * model.py::ModelMetadata` has no `provider_url`), so this table is the
 * frontend's own mapping and stays editable as providers change.
 */

/** The smallest shape needed to resolve a link. */
export interface LinkableModel {
  model_id?: string | null;
  model_name?: string | null;
  provider?: string | null;
}

interface ProviderLinkConfig {
  /** Canonical provider name as the backend reports it. */
  id: string;
  /** Human label for the UI. */
  label: string;
  /** The provider's own chat/playground entry point. */
  chatUrl: string;
  /**
   * Optional per-model page, when the provider exposes a stable public
   * page for a specific model. Keyed by model id, matched exactly.
   */
  modelPages?: Record<string, string>;
  /**
   * Whether the provider officially supports passing a prompt via the
   * URL. `template` is only meaningful when this is true; `null` means
   * "open the page normally and copy the prompt instead".
   */
  promptUrlTemplate: string | null;
  /** Shown in the UI when the user is told to paste instead. */
  pasteHint: string;
}

/**
 * Provider destinations.
 *
 * `promptUrlTemplate` is `null` everywhere except OpenAI's ChatGPT,
 * whose `?q=` parameter is a documented, supported behaviour. Every
 * other provider is opened plainly with the prompt copied to the
 * clipboard, because none of them document a prefill parameter.
 */
export const PROVIDER_LINKS: Record<string, ProviderLinkConfig> = {
  openai: {
    id: 'openai',
    label: 'OpenAI',
    chatUrl: 'https://chatgpt.com/',
    // ChatGPT officially accepts a prompt via `?q=`.
    promptUrlTemplate: 'https://chatgpt.com/?q={prompt}',
    pasteHint: 'ChatGPT opens with your prompt ready to send.',
  },
  anthropic: {
    id: 'anthropic',
    label: 'Anthropic',
    chatUrl: 'https://claude.ai/new',
    // Claude has no documented URL prefill parameter.
    promptUrlTemplate: null,
    pasteHint: 'Prompt copied. Paste it into Claude.',
  },
  google: {
    id: 'google',
    label: 'Google',
    chatUrl: 'https://gemini.google.com/app',
    // Gemini has no documented URL prefill parameter.
    promptUrlTemplate: null,
    pasteHint: 'Prompt copied. Paste it into Gemini.',
  },
  groq: {
    id: 'groq',
    label: 'Groq',
    chatUrl: 'https://console.groq.com/playground',
    // The playground has no documented URL prefill parameter.
    promptUrlTemplate: null,
    pasteHint: 'Prompt copied. Paste it into the Groq playground.',
  },
};

/** Fallback for a provider with no entry above: the provider's site. */
const UNKNOWN_PROVIDER: ProviderLinkConfig = {
  id: 'unknown',
  label: 'Provider site',
  chatUrl: 'https://huggingface.co/chat',
  promptUrlTemplate: null,
  pasteHint: 'Prompt copied. Paste it into the model you were sent to.',
};

function normalise(value: string | null | undefined): string {
  return (value ?? '').trim().toLowerCase();
}

export function providerConfig(provider: string | null | undefined): ProviderLinkConfig {
  const key = normalise(provider);
  if (PROVIDER_LINKS[key]) return PROVIDER_LINKS[key];
  return { ...UNKNOWN_PROVIDER, label: provider?.trim() || 'Provider' };
}

/**
 * Whether a provider is one this table actually knows how to link to.
 * Used to decide between linking somewhere real and hiding the action.
 */
export function isKnownProvider(provider: string | null | undefined): boolean {
  return normalise(provider) in PROVIDER_LINKS;
}

/**
 * NOTE: the provider is deliberately never inferred from a model id.
 *
 * Ids look namespaced (`openai/gpt-oss-20b`), which invites reading the
 * prefix as the provider. It is not. That prefix is the model *author*;
 * the live registry serves the same model from Groq. Callers resolve the
 * provider from `GET /models` via `useModelProvider` and pass it in
 * explicitly, so a wrong guess cannot silently become a wrong link.
 */

/** True only when the provider officially supports a prompt-carrying URL. */
export function supportsPromptPrefill(model: LinkableModel): boolean {
  return providerConfig(model.provider).promptUrlTemplate !== null;
}

/**
 * Where "open the recommended model" should take the user.
 *
 * Prefers a model-specific page when one is configured, otherwise the
 * provider's chat entry point. Returns `null` for a model with no
 * usable provider, so the caller can hide the action rather than
 * navigate somewhere meaningless.
 */
export function getModelUrl(model: LinkableModel): string | null {
  // Only link to a provider this table actually configures. Sending the
  // user to a generic fallback for an unrecognised provider would be a
  // broken promise dressed as a working button.
  if (!isKnownProvider(model.provider)) return null;
  const config = providerConfig(model.provider);
  const modelId = normalise(model.model_id);
  const specific = modelId ? config.modelPages?.[modelId] : undefined;
  return specific ?? config.chatUrl;
}

/**
 * A prompt-carrying URL, or `null` when the provider does not support
 * one. Callers must treat `null` as "copy the prompt instead" — see
 * `supportsPromptPrefill`.
 */
export function getPromptUrl(model: LinkableModel, prompt: string): string | null {
  const template = providerConfig(model.provider).promptUrlTemplate;
  if (!template) return null;
  return template.replace('{prompt}', encodeURIComponent(prompt));
}

export interface ModelLinkResult {
  /** Destination for the "Open model" action. */
  url: string | null;
  /** The link carries the prompt itself. */
  carriesPrompt: boolean;
  /** What to tell the user when the prompt was copied rather than sent. */
  pasteHint: string;
  providerLabel: string;
}

/**
 * Resolves the action for a recommended model in one call, so a
 * component never has to branch on prefill support itself.
 */
export function resolveModelLink(model: LinkableModel, prompt?: string | null): ModelLinkResult {
  const config = providerConfig(model.provider);
  const known = isKnownProvider(model.provider);
  const trimmed = prompt?.trim() ?? '';
  if (known && trimmed.length > 0 && config.promptUrlTemplate) {
    return {
      url: getPromptUrl(model, trimmed),
      carriesPrompt: true,
      pasteHint: config.pasteHint,
      providerLabel: config.label,
    };
  }
  return {
    url: getModelUrl(model),
    carriesPrompt: false,
    pasteHint: config.pasteHint,
    providerLabel: config.label,
  };
}
