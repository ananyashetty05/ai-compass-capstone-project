/**
 * Markdown table wrapper.
 *
 * `remark-gfm` already turns a pipe table into a real `<table>`; the only
 * thing missing is a scroll container. A wide table in a narrow column
 * would otherwise force the entire page sideways, so the table is capped
 * to its column and scrolls inside it instead. The wrapper is focusable
 * so a keyboard user can reach the overflow.
 */
import type { ReactNode } from 'react';

export function MarkdownTable({ children }: { children: ReactNode }) {
  return (
    <div className="md-table-wrap" tabIndex={0} role="region" aria-label="Table, scrolls horizontally">
      <table className="md-table">{children}</table>
    </div>
  );
}
