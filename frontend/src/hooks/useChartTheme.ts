/**
 * Resolves the design-token chart palette from the document so Recharts
 * receives concrete colours while the source of truth stays in CSS.
 * Re-runs whenever the resolved theme or contrast mode changes.
 */
import { useEffect, useMemo, useState } from 'react';

export interface ChartTheme {
  series: string[];
  grid: string;
  axis: string;
  text: string;
  surface: string;
  positive: string;
  negative: string;
  neutral: string;
}

const SERIES_VARS = [
  '--chart-series-1',
  '--chart-series-2',
  '--chart-series-3',
  '--chart-series-4',
  '--chart-series-5',
] as const;

function readVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value.length > 0 ? value : fallback;
}

function readTheme(): ChartTheme {
  return {
    series: SERIES_VARS.map((name, index) => readVar(name, ['#007aff', '#409cff', '#0057b8', '#727d8c', '#bbc4d0'][index])),
    grid: readVar('--chart-grid', '#e9edf3'),
    axis: readVar('--chart-axis', '#9aa4b2'),
    text: readVar('--color-text-secondary', '#505968'),
    surface: readVar('--color-surface', '#ffffff'),
    positive: readVar('--chart-positive', '#007aff'),
    negative: readVar('--chart-negative', '#505968'),
    neutral: readVar('--chart-neutral', '#727d8c'),
  };
}

/** Attribute values that can change the resolved palette. */
function paletteSignature(): string {
  if (typeof document === 'undefined') return 'ssr';
  const root = document.documentElement;
  return `${root.dataset.theme ?? 'light'}|${root.dataset.contrast ?? 'normal'}|${root.dataset.textScale ?? 'default'}`;
}

export function useChartTheme(): ChartTheme {
  const [signature, setSignature] = useState(paletteSignature);

  useEffect(() => {
    const check = () => setSignature(paletteSignature());
    const observer = new MutationObserver(check);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'data-contrast', 'data-text-scale'] });
    return () => observer.disconnect();
  }, []);

  return useMemo(() => {
    // `signature` is read so the palette is re-read exactly when the
    // theme, contrast or text-scale attribute changes; the observer
    // above is the only thing that can change it.
    void signature;
    return readTheme();
  }, [signature]);
}
