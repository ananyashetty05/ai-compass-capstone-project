/**
 * AI Compass — Authentication & profile API.
 */
import { get, post, put } from './http';
import type {
  AuthResponse,
  GroupDefaults,
  GroupOption,
  RegisterPayload,
  RoutingPreferences,
  UpdateProfilePayload,
  UserProfile,
} from '../types';

export type { RegisterPayload } from '../types';

export function login(email: string, password: string, signal?: AbortSignal): Promise<AuthResponse> {
  return post<AuthResponse>('/auth/login', { email, password }, signal);
}

export function register(payload: RegisterPayload, signal?: AbortSignal): Promise<AuthResponse> {
  return post<AuthResponse>('/auth/register', payload, signal);
}

export function getGroupOptions(signal?: AbortSignal): Promise<GroupOption[]> {
  return get<GroupOption[]>('/profile/groups', { signal });
}

export function getMe(signal?: AbortSignal): Promise<UserProfile> {
  return get<UserProfile>('/auth/me', { signal });
}

export function updatePreferences(
  routingPreferences: RoutingPreferences,
  signal?: AbortSignal,
): Promise<UserProfile> {
  return put<UserProfile>('/profile/preferences', { routing_preferences: routingPreferences }, signal);
}

export function updateProfile(payload: UpdateProfilePayload, signal?: AbortSignal): Promise<UserProfile> {
  return put<UserProfile>('/profile', payload, signal);
}

export function listGroups(signal?: AbortSignal): Promise<GroupOption[]> {
  return getGroupOptions(signal);
}

export function getGroupDefaults(group: string, signal?: AbortSignal): Promise<GroupDefaults> {
  return get<GroupDefaults>(`/profile/group-defaults/${encodeURIComponent(group)}`, { signal });
}
