/** Client-side validation for the sign-in / sign-up forms (mirrors the backend rules). */
export const MIN_PASSWORD_LENGTH = 8;
export const MAX_PASSWORD_LENGTH = 128;

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;

export function validateName(value: string): string | null {
  const v = value.trim();
  if (!v) return 'Enter your name.';
  if (v.length > 100) return 'Use 100 characters or fewer.';
  return null;
}

export function validateEmail(value: string): string | null {
  const v = value.trim();
  if (!v) return 'Enter your email address.';
  if (v.length > 254 || !EMAIL_RE.test(v)) return 'Enter a valid email address, like name@example.com.';
  return null;
}

export function validateNewPassword(value: string): string | null {
  if (!value) return 'Create a password.';
  if (value.length < MIN_PASSWORD_LENGTH) return `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
  if (value.length > MAX_PASSWORD_LENGTH) return `Use ${MAX_PASSWORD_LENGTH} characters or fewer.`;
  return null;
}

export function validateConfirm(password: string, confirm: string): string | null {
  if (!confirm) return 'Re-enter your password.';
  if (confirm !== password) return 'The passwords do not match.';
  return null;
}

export interface PasswordStrength {
  /** 0 (empty) to 4 (strong). */
  score: 0 | 1 | 2 | 3 | 4;
  label: string;
}

/** Simple length + variety heuristic; guidance only, never blocks sign-up beyond the minimum length. */
export function passwordStrength(value: string): PasswordStrength {
  if (!value) return { score: 0, label: '' };
  let points = 0;
  if (value.length >= MIN_PASSWORD_LENGTH) points += 1;
  if (value.length >= 12) points += 1;
  if (/[a-z]/.test(value) && /[A-Z]/.test(value)) points += 1;
  if (/\d/.test(value) && /[^A-Za-z0-9]/.test(value)) points += 1;
  const score = Math.max(1, points) as 1 | 2 | 3 | 4;
  return { score, label: ['', 'Weak', 'Fair', 'Good', 'Strong'][score] };
}
