/**
 * Number, currency and duration formatting.
 *
 * Every formatter distinguishes "no value" from "zero": a null or
 * non-finite input always yields the `Unavailable` label rather than
 * a fabricated 0.
 */
import { UNAVAILABLE } from '../types';

function isPresent(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/** 0.7342 → "73.4%" */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (!isPresent(value)) return UNAVAILABLE;
  return `${(value * 100).toFixed(digits)}%`;
}

/** 0.7342 → "0.734" (raw, for compact numeric columns) */
export function formatScore(value: number | null | undefined, digits = 3): string {
  if (!isPresent(value)) return UNAVAILABLE;
  return value.toFixed(digits);
}

/** 0.000013 → "$0.000013" — full precision for per-request cost. */
export function formatUsd(value: number | null | undefined, digits = 6): string {
  if (!isPresent(value)) return UNAVAILABLE;
  if (value === 0) return '$0.00';
  if (value < 0.000001) return `$${value.toExponential(2)}`;
  return `$${value.toFixed(digits)}`;
}

/** 0.0075 → "$0.0075 / 1K tokens" */
export function formatCostPerThousand(value: number | null | undefined): string {
  if (!isPresent(value)) return UNAVAILABLE;
  return `$${value.toFixed(4)} / 1K`;
}

/** 812.44 → "812 ms" · 2410 → "2.41 s" */
export function formatDuration(ms: number | null | undefined): string {
  if (!isPresent(ms)) return UNAVAILABLE;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)} s`;
  return `${(ms / 60_000).toFixed(2)} min`;
}

export function formatSeconds(seconds: number | null | undefined): string {
  if (!isPresent(seconds)) return UNAVAILABLE;
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  return `${seconds.toFixed(2)} s`;
}

export function formatInteger(value: number | null | undefined): string {
  if (!isPresent(value)) return UNAVAILABLE;
  return Math.round(value).toLocaleString('en-US');
}

export function formatNumber(value: number | null | undefined, digits = 1): string {
  if (!isPresent(value)) return UNAVAILABLE;
  return value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function formatTokens(value: number | null | undefined): string {
  if (!isPresent(value)) return UNAVAILABLE;
  return `${Math.round(value).toLocaleString('en-US')} tokens`;
}

/** ISO timestamp → locale string; null-safe. */
export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return UNAVAILABLE;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return UNAVAILABLE;
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return UNAVAILABLE;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return UNAVAILABLE;
  return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: '2-digit' });
}

/** `distributed_systems` → `Distributed systems` */
export function humanizeToken(value: string | null | undefined): string {
  if (!value) return UNAVAILABLE;
  const cleaned = value.replace(/[_-]+/g, ' ').trim();
  if (cleaned.length === 0) return UNAVAILABLE;
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1).toLowerCase();
}

/** `llama-3.1-70b` → "Llama 3.1 70b" for display only; the id stays visible. */
export function humanizeModelName(name: string): string {
  return name
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => (/^\d/.test(part) ? part : part.charAt(0).toUpperCase() + part.slice(1).toLowerCase()))
    .join(' ');
}

export function truncate(value: string, max: number): string {
  if (value.length <= max) return value;
  return `${value.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}

/** Greeting used on the dashboard, derived from the viewer's local clock. */
export function greeting(date = new Date()): string {
  const hour = date.getHours();
  if (hour < 5) return 'Good evening';
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

export function initials(name: string | null | undefined): string {
  if (!name) return '?';
  const trimmed = name.trim();
  if (trimmed.length === 0) return '?';
  const parts = trimmed.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase();
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** Safe percentage 0–100 for meter widths. */
export function toPercent(value: number | null | undefined): number {
  if (!isPresent(value)) return 0;
  return clamp(value * 100, 0, 100);
}

export function isPresentNumber(value: number | null | undefined): value is number {
  return isPresent(value);
}

/**
 * Recharts hands tooltip and label formatters a `ValueType`, which may
 * be a number, a string or an array. Narrow it to a number, or null
 * when the value is not usable, so formatters can delegate to the
 * null-safe helpers above instead of asserting a type.
 */
export function coerceNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}
