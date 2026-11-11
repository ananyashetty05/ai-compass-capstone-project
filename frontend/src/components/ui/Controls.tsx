import type { ReactNode } from 'react';
import { AlertCircle, Check, Minus } from 'lucide-react';
import { initials } from '../../utils/format';
import { Button } from './Button';

export interface AvatarProps {
  name: string | null | undefined;
  size?: 'sm' | 'md' | 'lg';
  /** Hidden from assistive tech when adjacent text already names the user. */
  decorative?: boolean;
}

export function Avatar({ name, size = 'md', decorative }: AvatarProps) {
  return (
    <span className="avatar" data-size={size === 'md' ? undefined : size} aria-hidden={decorative || undefined}>
      {initials(name)}
    </span>
  );
}

export function AvatarButton({
  name,
  detail,
  onClick,
  expanded,
  controls,
}: {
  name: string;
  detail?: string;
  onClick: () => void;
  expanded: boolean;
  controls: string;
}) {
  return (
    <button
      type="button"
      className="avatar-button"
      onClick={onClick}
      aria-expanded={expanded}
      aria-haspopup="menu"
      aria-controls={controls}
    >
      <Avatar name={name} />
      <span className="avatar-button-text">
        <span className="avatar-button-name">{name}</span>
        {detail ? <span className="avatar-button-meta">{detail}</span> : null}
      </span>
    </button>
  );
}

export function CheckboxRow({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label className="checkbox-row">
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
      <span className="checkbox-text">
        <span>{label}</span>
        {description ? <small>{description}</small> : null}
      </span>
    </label>
  );
}

export function SwitchRow({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className="switch"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
    >
      <span className="checkbox-text">
        <span>{label}</span>
        {description ? <small>{description}</small> : null}
      </span>
      <span className="switch-track" aria-hidden="true">
        <span className="switch-thumb" />
      </span>
    </button>
  );
}

/* ------------------------------------------------------------------ *
 * Save-state bar — communicates unsaved work without an alert
 * ------------------------------------------------------------------ */

export type SaveState = 'idle' | 'dirty' | 'saving' | 'saved' | 'error';

export function SaveStateBar({
  state,
  message,
  onSave,
  onReset,
  saveLabel = 'Save changes',
}: {
  state: SaveState;
  message?: string;
  onSave: () => void;
  onReset: () => void;
  saveLabel?: string;
}) {
  const dirty = state === 'dirty';
  const busy = state === 'saving';

  return (
    <div className="save-bar">
      <p className="save-bar-status" data-dirty={dirty || undefined} role="status" aria-live="polite">
        {busy ? (
          <>
            <span className="spinner" aria-hidden="true" /> Saving…
          </>
        ) : state === 'saved' ? (
          <>
            <Check aria-hidden="true" /> All changes saved
          </>
        ) : state === 'error' ? (
          <>
            <AlertCircle aria-hidden="true" /> {message ?? 'Changes could not be saved.'}
          </>
        ) : dirty ? (
          <>
            <AlertCircle aria-hidden="true" /> {message ?? 'You have unsaved changes.'}
          </>
        ) : (
          <>
            <Minus aria-hidden="true" /> No unsaved changes
          </>
        )}
      </p>
      <div className="save-bar-actions">
        <Button variant="ghost" size="sm" onClick={onReset} disabled={!dirty || busy}>
          Discard
        </Button>
        <Button variant="primary" size="sm" onClick={onSave} disabled={!dirty || busy} loading={busy}>
          {saveLabel}
        </Button>
      </div>
    </div>
  );
}
