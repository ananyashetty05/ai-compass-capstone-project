import { get, post } from './http';
import type { FeedbackSubmission, FeedbackRecord, LearningState } from '../types';

export function submitFeedback(sub: FeedbackSubmission, signal?: AbortSignal): Promise<FeedbackRecord> {
  return post<FeedbackRecord>('/feedback', sub, signal);
}

export function getFeedback(limit = 50, signal?: AbortSignal): Promise<FeedbackRecord[]> {
  return get<FeedbackRecord[]>('/feedback', { signal, params: { limit: String(limit) } });
}

export function getLearningState(signal?: AbortSignal): Promise<LearningState> {
  return get<LearningState>('/feedback/learning', { signal });
}
