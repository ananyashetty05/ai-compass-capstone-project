import { forwardRef, useId } from 'react';
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';
import { AlertCircle } from 'lucide-react';
import { cn } from '../../utils/cn';

/* ------------------------------------------------------------------ *
 * Field wrapper — label, hint, error wired with aria-describedby
 * ------------------------------------------------------------------ */

export interface FieldProps {
  label: ReactNode;
  /** Renders `id` and ties label/control together. */
  htmlFor: string;
  hint?: ReactNode;
  error?: string | null;
  required?: boolean;
  /** Rendered on the right of the label row, e.g. a character count. */
  trailing?: ReactNode;
  /**
   * Keeps the label for assistive technology but removes it visually.
   * Use when a panel heading already names the control, so the same
   * words are not read and seen twice.
   */
  hideLabel?: boolean;
  children: ReactNode;
}

export function Field({
  label,
  htmlFor,
  hint,
  error,
  required,
  trailing,
  hideLabel,
  children,
}: FieldProps) {
  return (
    <div className="field">
      <label className={cn('field-label', hideLabel && 'sr-only')} htmlFor={htmlFor}>
        <span>
          {label}
          {required ? (
            <>
              <span className="field-required" aria-hidden="true">
                {' '}
                *
              </span>
              <span className="sr-only"> (required)</span>
            </>
          ) : null}
        </span>
        {trailing}
      </label>
      {children}
      {error ? (
        <p className="field-error" id={`${htmlFor}-error`}>
          <AlertCircle aria-hidden="true" />
          <span>{error}</span>
        </p>
      ) : hint ? (
        <p className="field-hint" id={`${htmlFor}-hint`}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Text input
 * ------------------------------------------------------------------ */

export interface TextInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  leadingIcon?: ReactNode;
  /** Trailing control, e.g. a show/hide password button. */
  trailing?: ReactNode;
  containerClassName?: string;
  /** Visually hides the label; see `Field`'s `hideLabel`. */
  hideLabel?: boolean;
}

export const TextInput = forwardRef<HTMLInputElement, TextInputProps>(function TextInput(
  { label, hint, error, leadingIcon, trailing, id, required, className, containerClassName, hideLabel, ...rest },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const describedBy = error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined;

  return (
    <Field label={label} htmlFor={inputId} hint={hint} error={error} required={required} hideLabel={hideLabel}>
      <div
        className={cn('input-shell', containerClassName)}
        data-invalid={error ? 'true' : undefined}
        data-has-icon={leadingIcon ? 'true' : undefined}
        data-has-affix={trailing ? 'true' : undefined}
      >
        {leadingIcon ? (
          <span className="input-icon" aria-hidden="true">
            {leadingIcon}
          </span>
        ) : null}
        <input
          ref={ref}
          id={inputId}
          className={cn('input', className)}
          aria-invalid={error ? 'true' : undefined}
          aria-describedby={describedBy}
          required={required}
          {...rest}
        />
        {trailing ? <span className="input-affix">{trailing}</span> : null}
      </div>
    </Field>
  );
});

/* ------------------------------------------------------------------ *
 * Textarea
 * ------------------------------------------------------------------ */

export interface TextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  /** Renders a character count derived from `value`. */
  showCount?: boolean;
  countUnit?: string;
  /** Visually hides the label; see `Field`'s `hideLabel`. */
  hideLabel?: boolean;
}

export const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(function TextArea(
  { label, hint, error, showCount, countUnit = 'characters', id, required, className, value, hideLabel, ...rest },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const describedBy = error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined;
  const length = typeof value === 'string' ? value.length : 0;

  return (
    <Field
      label={label}
      htmlFor={inputId}
      hint={hint}
      error={error}
      required={required}
      hideLabel={hideLabel}
      trailing={
        showCount ? (
          <span className="text-numeric text-xs text-muted" aria-live="off">
            {length.toLocaleString('en-US')} {countUnit}
          </span>
        ) : undefined
      }
    >
      <textarea
        ref={ref}
        id={inputId}
        className={cn('textarea', className)}
        value={value}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={describedBy}
        required={required}
        {...rest}
      />
    </Field>
  );
});

/* ------------------------------------------------------------------ *
 * Select — native element with a labelled group
 * ------------------------------------------------------------------ */

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'children' | 'onChange' | 'className'> {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  options: readonly { value: string; label: string; disabled?: boolean }[];
  onValueChange?: (value: string) => void;
  placeholder?: string;
  containerClassName?: string;
  className?: string;
}

export function Select({
  label,
  hint,
  error,
  options,
  onValueChange,
  placeholder,
  id,
  className,
  containerClassName,
  required,
  ...rest
}: SelectProps) {
  const generatedId = useId();
  const selectId = id ?? generatedId;
  const describedBy = error ? `${selectId}-error` : hint ? `${selectId}-hint` : undefined;

  return (
    <Field label={label} htmlFor={selectId} hint={hint} error={error} required={required}>
      <select
        id={selectId}
        className={cn('select', className, containerClassName)}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={describedBy}
        onChange={(event) => onValueChange?.(event.target.value)}
        {...rest}
      >
        {placeholder ? <option value="">{placeholder}</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
    </Field>
  );
}
