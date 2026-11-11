import { useId } from 'react';
import { BandIndicator } from './ScoreBar';

export interface SliderProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  /** Short explanation of what this objective controls. */
  description?: string;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  /** Formats the readout; defaults to a percentage. */
  formatValue?: (value: number) => string;
  id?: string;
}

/**
 * Accessible range control.
 *
 * Uses a native `<input type="range">` so keyboard, touch and assistive
 * technology support come for free. The value is exposed through
 * `aria-valuetext` in words, not just as a number.
 */
export function Slider({
  label,
  value,
  onChange,
  description,
  min = 0,
  max = 1,
  step = 0.05,
  disabled,
  formatValue,
  id,
}: SliderProps) {
  const generatedId = useId();
  const sliderId = id ?? generatedId;
  const descriptionId = `${sliderId}-description`;
  const percent = Math.round(((value - min) / (max - min)) * 100);
  const text = formatValue ? formatValue(value) : `${Math.round(value * 100)}%`;
  const level =
    value >= 0.75 ? 'High' : value >= 0.4 ? 'Moderate' : value <= 0.05 ? 'Not prioritised' : 'Low';

  return (
    <div className="slider">
      <div className="slider-head">
        <label className="slider-label" htmlFor={sliderId}>
          {label}
        </label>
        <span className="slider-value">
          {text} <span className="sr-only">({level})</span>
        </span>
      </div>
      <input
        id={sliderId}
        className="slider-input"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
        aria-describedby={description ? descriptionId : undefined}
        aria-valuetext={`${text}, ${level}`}
        style={{ ['--slider-percent' as string]: `${percent}%` }}
      />
      {description ? (
        <p className="slider-description" id={descriptionId}>
          {description}
        </p>
      ) : null}
      <BandIndicator value={value} />
    </div>
  );
}
