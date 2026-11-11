/**
 * Numeric helpers for score presentation.
 */
import { clamp } from './format';

export type ScoreBand = 'strong' | 'moderate' | 'weak' | 'unknown';

/**
 * Band a 0–1 score for textual labelling. Colour is applied by the
 * caller from a design token; the band itself is always rendered as
 * text so meaning never depends on colour alone.
 */
export function scoreBand(value: number | null | undefined): ScoreBand {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'unknown';
  if (value >= 0.75) return 'strong';
  if (value >= 0.45) return 'moderate';
  return 'weak';
}

export function bandLabel(band: ScoreBand): string {
  switch (band) {
    case 'strong':
      return 'Strong';
    case 'moderate':
      return 'Moderate';
    case 'weak':
      return 'Weak';
    default:
      return 'Unavailable';
  }
}

/** CSS custom property reference for a band — resolved by the token layer. */
export function bandToken(band: ScoreBand): string {
  switch (band) {
    case 'strong':
      return 'var(--color-success)';
    case 'moderate':
      return 'var(--color-warning)';
    case 'weak':
      return 'var(--color-danger)';
    default:
      return 'var(--color-text-disabled)';
  }
}

export function average(values: readonly number[]): number | null {
  const usable = values.filter((v) => Number.isFinite(v));
  if (usable.length === 0) return null;
  return usable.reduce((sum, v) => sum + v, 0) / usable.length;
}

export function sum(values: readonly number[]): number | null {
  const usable = values.filter((v) => Number.isFinite(v));
  if (usable.length === 0) return null;
  return usable.reduce((acc, v) => acc + v, 0);
}

export function ratio(numerator: number, denominator: number): number | null {
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator === 0) return null;
  return numerator / denominator;
}

export function max(values: readonly number[]): number | null {
  const usable = values.filter((v) => Number.isFinite(v));
  return usable.length === 0 ? null : Math.max(...usable);
}

export function min(values: readonly number[]): number | null {
  const usable = values.filter((v) => Number.isFinite(v));
  return usable.length === 0 ? null : Math.min(...usable);
}

export function toPercentScale(value: number | null | undefined, digits = 1): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  return Number((clamp(value, 0, 1) * 100).toFixed(digits));
}

/** Normalise a set of values into 0–1 weights summing to 1. */
export function normaliseWeights(weights: Record<string, number>): Record<string, number> {
  const entries = Object.entries(weights).filter(([, v]) => Number.isFinite(v) && v > 0);
  const total = entries.reduce((acc, [, v]) => acc + v, 0);
  if (total === 0) return {};
  return Object.fromEntries(entries.map(([k, v]) => [k, Number((v / total).toFixed(4))]));
}
