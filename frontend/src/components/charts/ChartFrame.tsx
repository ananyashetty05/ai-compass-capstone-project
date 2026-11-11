/**
 * ChartFrame — the accessible wrapper every Recharts surface uses.
 *
 * Recharts renders SVG, which is invisible to a screen reader unless the
 * data is also exposed as text. This component always renders:
 *  - a title and description,
 *  - a visible summary of the series,
 *  - a `<table>` alternative (collapsed behind a disclosure) holding the
 *    same values, so the chart is never the only way to read the data.
 *
 * `role="img"` with an `aria-label` marks the SVG itself as a single
 * image, which stops a screen reader from announcing every tick.
 */
import { useId } from 'react';
import type { ReactNode } from 'react';
import { InfoHint } from '../ui/Tooltip';
import { useChartTheme } from '../../hooks/useChartTheme';
import { UNAVAILABLE } from '../../types';

export interface ChartSeriesPoint {
  /** Row label, e.g. a model id or a score dimension. */
  label: string;
  value: number | null;
  /** Optional second value for grouped bars. */
  secondaryValue?: number | null;
  /**
   * Explicit per-series values. Multi-series charts pass this so the
   * table alternative has exactly one column per series; single-series
   * charts can leave it out.
   */
  values?: readonly (number | null)[];
}

export interface ChartFrameProps {
  title: string;
  description?: ReactNode;
  /** One-line takeaway rendered above the chart. */
  summary?: string;
  series: readonly string[];
  data: readonly ChartSeriesPoint[];
  secondarySeries?: string;
  /** Formats values for the table and the tooltip. */
  format: (value: number) => string;
  height?: number;
  /** Any Recharts element. */
  children: (theme: ReturnType<typeof useChartTheme>, barId: string) => ReactNode;
  /** Renders the accessible fallback when there is nothing to plot. */
  emptyMessage?: string;
}

export function ChartFrame({
  title,
  description,
  summary,
  series,
  data,
  secondarySeries,
  format,
  height = 260,
  children,
  emptyMessage = 'No data is available for this chart.',
}: ChartFrameProps) {
  const theme = useChartTheme();
  const titleId = useId();
  const descId = useId();

  /**
   * One entry per series, in series order, for a single row. Keeping
   * this in one place guarantees the table body always has the same
   * number of cells as the header.
   */
  const valuesFor = (point: ChartSeriesPoint): readonly (number | null)[] => {
    if (point.values) return point.values;
    return secondarySeries ? [point.value, point.secondaryValue ?? null] : [point.value];
  };

  const hasData = data.some((point) => valuesFor(point).some((value) => value !== null));
  const maxima = data
    .flatMap((point) => valuesFor(point))
    .filter((value): value is number => value !== null && Number.isFinite(value));
  const maxValue = maxima.length > 0 ? Math.max(...maxima) : null;

  const tableId = useId();

  return (
    <figure className="chart-frame" aria-labelledby={titleId} aria-describedby={descId}>
      <div className="chart-header">
        <div className="chart-title-group">
          <figcaption className="chart-title" id={titleId}>
            {title}
            {description ? <InfoHint content={description} label={`About ${title}`} /> : null}
          </figcaption>
          {summary ? <p className="chart-summary">{summary}</p> : null}
        </div>
        <ul className="chart-legend">
          {series.map((name, index) => (
            <li key={name}>
              <span
                className="chart-legend-swatch"
                style={{ background: theme.series[index % theme.series.length] }}
                aria-hidden="true"
              />
              {name}
            </li>
          ))}
        </ul>
      </div>

      <p className="sr-only" id={descId}>
        {description ?? `${title}. ${series.join(' and ')} across ${data.length} categories.`}
        {hasData && maxValue !== null
          ? ` The highest value is ${format(maxValue)}.`
          : ' No values are available.'}
      </p>

      {hasData ? (
        <div
          className="chart-canvas"
          style={{ ['--chart-height' as string]: `${height}px` }}
          role="img"
          aria-label={summary ?? title}
        >
          {children(theme, `${titleId}-bar`)}
        </div>
      ) : (
        <p className="chart-fallback">{emptyMessage}</p>
      )}

      <details className="chart-table" id={tableId}>
        <summary>View as table</summary>
        <div className="table-wrap">
          <table className="data-table">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr>
                <th scope="col">Category</th>
                {series.map((name) => (
                  <th key={name} scope="col" className="cell-numeric">
                    {name}
                  </th>
                ))}
                {secondarySeries ? (
                  <th scope="col" className="cell-numeric">
                    {secondarySeries}
                  </th>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {data.map((point) => (
                <tr key={point.label}>
                  <th scope="row">{point.label}</th>
                  {valuesFor(point).map((value, index) => (
                    <td key={series[index] ?? index} className="cell-numeric">
                      {value === null || value === undefined || !Number.isFinite(value)
                        ? UNAVAILABLE
                        : format(value)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
