import { bandLabel, bandToken, scoreBand } from '../../utils/scores';
import { isPresentNumber, toPercent } from '../../utils/format';
import { UNAVAILABLE } from '../../types';

export interface ScoreBarProps {
  value: number | null | undefined;
  /** Accessible name, e.g. "Quality score for llama-3.1-70b". */
  label: string;
  /** Overrides the automatic band colouring. */
  color?: string;
  showValue?: boolean;
  compact?: boolean;
  digits?: number;
}

/**
 * A single 0–1 score.
 *
 * The bar is decorative (`aria-hidden`). The numeric value and a
 * qualitative band are always exposed as text, so the information
 * never depends on the length or colour of the bar. Missing values
 * read "Unavailable" — never 0.
 */
export function ScoreBar({ value, label, color, showValue = true, compact, digits = 0 }: ScoreBarProps) {
  const band = scoreBand(value);
  const available = isPresentNumber(value);
  const width = available ? toPercent(value) : 0;
  const display = available ? `${(value * 100).toFixed(digits)}%` : UNAVAILABLE;
  const textLabel = available ? `${label}: ${display}, ${bandLabel(band)}` : `${label}: ${UNAVAILABLE}`;

  return (
    <div className="score-bar" data-compact={compact || undefined}>
      <div className="score-track" aria-hidden="true">
        <div
          className="score-fill"
          style={{ width: `${width}%`, ['--score-color' as string]: color ?? bandToken(band) }}
        />
      </div>
      {showValue ? (
        <span className="score-value" data-unavailable={!available || undefined}>
          {display}
          <span className="sr-only">. {available ? bandLabel(band) : UNAVAILABLE}</span>
        </span>
      ) : null}
      <span className="sr-only">{textLabel}</span>
    </div>
  );
}

/** Decorative bar only — use when the numeric readout sits elsewhere. */
export function BandIndicator({ value, color }: { value: number; color?: string }) {
  const band = scoreBand(value);
  return (
    <div className="score-track" aria-hidden="true">
      <div
        className="score-fill"
        style={{
          width: `${toPercent(value)}%`,
          ['--score-color' as string]: color ?? bandToken(band),
        }}
      />
    </div>
  );
}

export interface DimensionRowProps {
  label: string;
  value: number | null | undefined;
  /** Longer meaning, surfaced to screen readers. */
  description?: string;
  color?: string;
  digits?: number;
  /** Unit suffix, e.g. "%" (default) or " ms". */
  suffix?: string;
}

/** Label + bar + numeric readout, used for score breakdowns. */
export function DimensionRow({ label, value, description, color, digits = 1, suffix = '%' }: DimensionRowProps) {
  const available = isPresentNumber(value);
  const display = available ? `${(value * 100).toFixed(digits)}${suffix}` : UNAVAILABLE;

  return (
    <div className="dimension-row">
      <span className="dimension-label">
        {label}
        {description ? <span className="sr-only">. {description}</span> : null}
      </span>
      <ScoreBar value={value} label={label} color={color} digits={digits} />
      {available ? <span className="sr-only">{` ${display}`}</span> : null}
    </div>
  );
}
