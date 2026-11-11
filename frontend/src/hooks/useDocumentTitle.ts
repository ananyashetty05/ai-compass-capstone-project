import { useEffect } from 'react';

const SUFFIX = 'AI Compass';

/**
 * Keeps `document.title` in sync with the current page so the tab,
 * history entries and screen-reader announcements stay distinguishable.
 */
export function useDocumentTitle(title: string): void {
  useEffect(() => {
    const previous = document.title;
    const pageTitle = title.trim();
    document.title = pageTitle
      ? pageTitle.endsWith(SUFFIX)
        ? pageTitle
        : `${pageTitle} · ${SUFFIX}`
      : SUFFIX;
    return () => {
      document.title = previous;
    };
  }, [title]);
}
