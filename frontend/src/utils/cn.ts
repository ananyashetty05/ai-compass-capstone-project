/**
 * Minimal class-name joiner.
 *
 * Accepts strings, falsy values and conditional maps so call sites stay
 * readable without pulling in a dependency.
 */
export type ClassValue = string | number | null | undefined | false | Record<string, boolean | undefined | null>;

export function cn(...values: ClassValue[]): string {
  const out: string[] = [];
  for (const value of values) {
    if (!value && value !== 0) continue;
    if (typeof value === 'string' || typeof value === 'number') {
      const text = String(value).trim();
      if (text) out.push(text);
    } else {
      for (const [key, enabled] of Object.entries(value)) {
        if (enabled) out.push(key);
      }
    }
  }
  return out.join(' ');
}
