import { useState } from 'react';
import type { InputHTMLAttributes, ReactNode, Ref } from 'react';
import { Eye, EyeOff, Lock } from 'lucide-react';
import { IconButton, TextInput } from '../ui';

export interface PasswordFieldProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type' | 'size'> {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  ref?: Ref<HTMLInputElement>;
}

/** Password input with an accessible show/hide toggle. */
export function PasswordField({ id, ref, ...props }: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);
  const fieldId = id ?? `pw-${String(props.name ?? 'password')}`;
  return (
    <TextInput
      {...props}
      ref={ref}
      id={fieldId}
      type={visible ? 'text' : 'password'}
      leadingIcon={<Lock />}
      trailing={
        <IconButton
          label={visible ? 'Hide password' : 'Show password'}
          size="sm"
          aria-pressed={visible}
          aria-controls={fieldId}
          icon={visible ? <EyeOff /> : <Eye />}
          onClick={() => setVisible((v) => !v)}
        />
      }
    />
  );
}
