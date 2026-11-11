/**
 * AI Compass — Routing API.
 *
 * The backend resolves the user profile from the bearer token, so no
 * user group or preference is ever sent per request.
 */
import { post } from './http';
import type { RouteRequest, RouteResponse } from '../types';

export function routeAndGenerate(payload: RouteRequest, signal?: AbortSignal): Promise<RouteResponse> {
  return post<RouteResponse>('/route-and-generate', payload, signal);
}
