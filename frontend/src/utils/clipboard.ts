/**
 * Copy text to the clipboard. Uses the async Clipboard API when the page is
 * allowed to, and falls back to a hidden textarea + execCommand otherwise
 * (non-secure origins, embedded previews, or a denied permission).
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through to the legacy path */
  }
  try {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none;';
    document.body.appendChild(area);
    const previous = document.activeElement as HTMLElement | null;
    area.select();
    area.setSelectionRange(0, text.length);
    const ok = document.execCommand('copy');
    document.body.removeChild(area);
    previous?.focus?.();
    return ok;
  } catch {
    return false;
  }
}
