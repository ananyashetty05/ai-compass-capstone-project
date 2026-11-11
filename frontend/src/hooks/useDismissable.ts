/**
 * Closes popovers on outside pointer interaction or Escape, and
 * reports arrow-key navigation for menu-like surfaces.
 */
import { useEffect } from 'react';
import type { RefObject } from 'react';

export function useDismissable(
  active: boolean,
  refs: ReadonlyArray<RefObject<HTMLElement | null>>,
  onDismiss: () => void,
  options: { escape?: boolean; pointer?: boolean } = {},
): void {
  const { escape = true, pointer = true } = options;

  useEffect(() => {
    if (!active) return;

    const handlePointer = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      const inside = refs.some((ref) => ref.current?.contains(target));
      if (!inside) onDismiss();
    };

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onDismiss();
      }
    };

    if (pointer) document.addEventListener('pointerdown', handlePointer, true);
    if (escape) document.addEventListener('keydown', handleKey, true);

    return () => {
      if (pointer) document.removeEventListener('pointerdown', handlePointer, true);
      if (escape) document.removeEventListener('keydown', handleKey, true);
    };
  }, [active, onDismiss, escape, pointer, refs]);
}
