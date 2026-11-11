/**
 * Resolves the provider that serves a model id.
 *
 * The routing payload returns a model id but no provider, and a model
 * id's prefix is the model's *author*, not the company serving it. The
 * live registry is the proof of this: `openai/gpt-oss-20b` is an
 * OpenAI-authored model served by Groq. Guessing the provider from the
 * prefix therefore sends the "open the recommended model" action to the
 * wrong company's site, which is a confident-looking dead end.
 *
 * So the registry wins: `GET /models` reports the real `provider` for
 * every id, and that is what this hook returns. The prefix is used only
 * as a last resort when the registry cannot be reached, and callers
 * treat a `null` result as "no link" rather than guessing further.
 */
import { useMemo } from 'react';
import { listModels } from '../services/models.service';
import type { ModelInfo } from '../types';
import { useAsync } from './useAsync';

/** One registry row, reduced to what a link needs. */
export type ProviderLookup = Record<string, string>;

function toLookup(list: ModelInfo[] | null): ProviderLookup {
  if (!list) return {};
  return Object.fromEntries(
    list
      .filter((model) => model.model_id && model.provider)
      .map((model) => [model.model_id, model.provider]),
  );
}

/**
 * @param modelId the id to resolve, e.g. `openai/gpt-oss-20b`
 * @returns the registry provider, or `null` when it cannot be
 *   established. A `null` provider means the caller should not render a
 *   link rather than falling back to the id prefix.
 */
export function useModelProvider(modelId: string | null | undefined): {
  provider: string | null;
  isLoading: boolean;
} {
  const registry = useAsync((signal) => listModels(signal), []);

  const provider = useMemo(() => {
    const id = (modelId ?? '').trim();
    if (!id) return null;
    return toLookup(registry.data)[id] ?? null;
  }, [modelId, registry.data]);

  return { provider, isLoading: registry.isLoading };
}
