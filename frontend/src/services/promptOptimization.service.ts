import { post } from './http';
import type { OptimizePromptRequest, OptimizePromptResponse } from '../types';

export function optimizePrompt(
  payload: OptimizePromptRequest,
  signal?: AbortSignal,
): Promise<OptimizePromptResponse> {
  return post<OptimizePromptResponse>('/optimize-prompt', payload, signal);
}
