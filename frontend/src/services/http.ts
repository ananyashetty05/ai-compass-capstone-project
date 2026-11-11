/**
 * AI Compass — HTTP client
 *
 * The single place where Axios is configured. Pages never import Axios.
 * Configuration comes from environment variables (VITE_API_BASE_URL) so
 * the same build works against local, staging and production backends.
 */
import axios from 'axios';
import type { AxiosError, AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from 'axios';

const DEVELOPMENT_API_URL = 'http://localhost:8080/api/v1';
const PRODUCTION_API_URL = '/api/v1';
const REQUEST_TIMEOUT_MS = 120_000;
const TOKEN_STORAGE_KEY = 'aicompass.auth.token';

/** Emitted when the API rejects our credentials so AuthContext can react. */
export const UNAUTHORIZED_EVENT = 'aicompass:unauthorized';

const rawBaseUrl = import.meta.env.VITE_API_BASE_URL;
const configuredBaseUrl = rawBaseUrl?.trim();
export const API_BASE_URL = (configuredBaseUrl || (import.meta.env.DEV ? DEVELOPMENT_API_URL : PRODUCTION_API_URL)).replace(
  /\/+$/,
  '',
);

/** True when the base URL is the local development fallback. */
export const IS_DEVELOPMENT_FALLBACK = !configuredBaseUrl && import.meta.env.DEV;

/* ------------------------------------------------------------------ *
 * Token storage
 *
 * The token is never logged, never placed in a URL, and never sent
 * anywhere other than the API origin configured above.
 * ------------------------------------------------------------------ */

export const tokenStore = {
  get(): string | null {
    try {
      return window.localStorage.getItem(TOKEN_STORAGE_KEY);
    } catch {
      /* Storage can be blocked (private mode, strict CSP). */
      return null;
    }
  },
  set(token: string): void {
    try {
      window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
    } catch {
      /* Non-fatal: the in-memory token still authenticates this session. */
    }
  },
  clear(): void {
    try {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    } catch {
      /* no-op */
    }
  },
};

/* ------------------------------------------------------------------ *
 * ApiError
 * ------------------------------------------------------------------ */

type StatusMessage = { status: number; message: string; hint?: string };

const STATUS_MESSAGES: Record<number, Omit<StatusMessage, 'status'>> = {
  400: { message: 'The request was rejected as invalid.', hint: 'Review the submitted values and try again.' },
  401: { message: 'Your session has expired.', hint: 'Sign in again to continue.' },
  403: { message: 'You do not have permission to perform this action.' },
  404: { message: 'The requested resource was not found.' },
  408: { message: 'The request timed out.', hint: 'The backend did not respond in time.' },
  409: { message: 'This resource already exists.' },
  422: { message: 'Some submitted values were rejected by the server.' },
  429: { message: 'Too many requests.', hint: 'Wait a moment before retrying.' },
  500: { message: 'The service encountered an unexpected error.' },
  502: { message: 'An upstream provider gateway returned an error.' },
  503: { message: 'A required AI provider is currently unavailable.' },
  504: { message: 'An upstream provider timed out.' },
};

export type ApiErrorKind = 'status' | 'network' | 'timeout' | 'canceled' | 'unknown';

/** Normalised, user-safe error surfaced by the API layer. */
export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly hint: string | undefined;
  /** Server-provided detail, already stringified. */
  readonly detail: string | undefined;

  constructor(params: {
    kind: ApiErrorKind;
    message: string;
    status?: number | null;
    hint?: string;
    detail?: string;
  }) {
    super(params.message);
    this.name = 'ApiError';
    this.kind = params.kind;
    this.status = params.status ?? null;
    this.hint = params.hint;
    this.detail = params.detail;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isRetriable(): boolean {
    return (
      this.kind === 'network' ||
      this.kind === 'timeout' ||
      this.status === null ||
      (this.status !== null && this.status >= 500)
    );
  }
}

function extractDetail(data: unknown): string | undefined {
  if (typeof data === 'string' && data.trim().length > 0) return data.trim();
  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>;
    if (typeof record.detail === 'string' && record.detail.trim().length > 0) return record.detail.trim();
  }
  return undefined;
}

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;

  if (axios.isCancel(error)) {
    return new ApiError({ kind: 'canceled', message: 'The request was cancelled.' });
  }

  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<unknown>;
    const status = axiosError.response?.status ?? null;

    if (axiosError.code === 'ECONNABORTED' || axiosError.code === 'ETIMEDOUT') {
      return new ApiError({
        kind: 'timeout',
        status,
        message: 'The request timed out.',
        hint: 'The backend or an AI provider did not respond in time.',
      });
    }

    if (!axiosError.response) {
      return new ApiError({
        kind: 'network',
        status: null,
        message: 'Cannot reach the AI Compass backend.',
        hint: `Check that the API at ${API_BASE_URL} is running and reachable.`,
      });
    }

    const known = status !== null ? STATUS_MESSAGES[status] : undefined;
    return new ApiError({
      kind: 'status',
      status,
      message: known?.message ?? 'The request could not be completed.',
      hint: known?.hint,
      detail: extractDetail(axiosError.response.data),
    });
  }

  if (error instanceof Error) {
    return new ApiError({ kind: 'unknown', message: error.message });
  }

  return new ApiError({ kind: 'unknown', message: 'An unexpected error occurred.' });
}

/* ------------------------------------------------------------------ *
 * Instance
 * ------------------------------------------------------------------ */

export const http: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: REQUEST_TIMEOUT_MS,
  headers: { Accept: 'application/json' },
});

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStore.get();
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`);
  }
  config.headers.set('X-Requested-With', 'AICompassWeb');
  return config;
});

http.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: unknown) => {
    const apiError = toApiError(error);
    if (apiError.isUnauthorized) {
      tokenStore.clear();
      window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT, { detail: { message: apiError.message } }));
    }
    return Promise.reject(apiError);
  },
);

/**
 * Every service function resolves to the response *body*, not the Axios
 * envelope, and always rejects with an `ApiError`.
 */
export async function get<T>(url: string, config?: { signal?: AbortSignal; params?: Record<string, string> }): Promise<T> {
  const response = await http.get<T>(url, { signal: config?.signal, params: config?.params });
  return response.data;
}

export async function post<T>(url: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await http.post<T>(url, body, { signal });
  return response.data;
}

export async function put<T>(url: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await http.put<T>(url, body, { signal });
  return response.data;
}

export async function del<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await http.delete<T>(url, { signal });
  return response.data;
}

/**
 * Human-readable message for any thrown value.
 * Prefers the server's own `detail` so the UI never invents wording.
 */
export function describeError(error: unknown, fallback = 'Something went wrong.'): { message: string; hint?: string } {
  if (error instanceof ApiError) {
    return {
      // The server's own `detail` is the authoritative wording and wins.
      // The hint is the status's own guidance, never the canned status
      // *message*: pairing a detail with it produced contradictions such as
      // "Invalid email or password" followed by "Your session has expired."
      message: error.detail ?? error.message,
      hint: error.hint,
    };
  }
  if (error instanceof Error && error.message) return { message: error.message };
  return { message: fallback };
}

export default http;
