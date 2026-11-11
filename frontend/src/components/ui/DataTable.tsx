import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react';

export type SortDirection = 'asc' | 'desc';

export interface ColumnDef<T> {
  id: string;
  header: string;
  /** Renders the cell. */
  cell: (row: T) => ReactNode;
  /** Omit for non-sortable columns. */
  sortValue?: (row: T) => number | string | null;
  numeric?: boolean;
  /** Hidden below the mobile card breakpoint. */
  secondary?: boolean;
  width?: string;
}

export interface DataTableProps<T> {
  caption: string;
  columns: ColumnDef<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  initialSort?: { columnId: string; direction: SortDirection };
  highlight?: (row: T) => boolean;
  /** Rendered instead of the table on narrow viewports. */
  renderCard: (row: T) => ReactNode;
  emptyState: ReactNode;
  /**
   * Drops the wrapper's own border and radius, so the table can sit
   * flush inside a surrounding surface that already has one — e.g. a
   * toolbar band above it.
   */
  flush?: boolean;
}

function compare(a: number | string | null, b: number | string | null): number {
  const aMissing = a === null || a === undefined || (typeof a === 'number' && !Number.isFinite(a));
  const bMissing = b === null || b === undefined || (typeof b === 'number' && !Number.isFinite(b));
  if (aMissing && bMissing) return 0;
  // Missing values always sort last regardless of direction.
  if (aMissing) return 1;
  if (bMissing) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), 'en', { numeric: true, sensitivity: 'base' });
}

/**
 * Sortable, screen-reader-friendly data table.
 *
 * Sorting is exposed through `aria-sort` and arrow-key interaction on
 * the header buttons, and the sort state is announced in a live region
 * so the result is not visual-only.
 */
export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  initialSort,
  highlight,
  renderCard,
  emptyState,
  flush,
}: DataTableProps<T>) {
  const [sort, setSort] = useState(initialSort ?? null);
  const [announcement, setAnnouncement] = useState('');

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const column = columns.find((c) => c.id === sort.columnId);
    if (!column?.sortValue) return rows;
    const value = column.sortValue;
    return [...rows].sort((a, b) => {
      const result = compare(value(a), value(b));
      return sort.direction === 'asc' ? result : -result;
    });
  }, [rows, sort, columns]);

  const activate = (column: ColumnDef<T>) => {
    if (!column.sortValue) return;
    const direction: SortDirection =
      sort?.columnId === column.id ? (sort.direction === 'desc' ? 'asc' : 'desc') : 'desc';
    setSort({ columnId: column.id, direction });
    setAnnouncement(`Table sorted by ${column.header}, ${direction === 'desc' ? 'descending' : 'ascending'}.`);
  };

  const ariaSort = (column: ColumnDef<T>): 'ascending' | 'descending' | 'none' => {
    if (!column.sortValue) return 'none';
    if (sort?.columnId !== column.id) return 'none';
    return sort.direction === 'desc' ? 'descending' : 'ascending';
  };

  if (rows.length === 0) return <>{emptyState}</>;

  return (
    <>
      {/* `data-table-wrap` marks this as the table that swaps to a record
          list on narrow viewports, so only it is hidden on mobile. */}
      <div className="table-wrap data-table-wrap" data-flush={flush ? 'true' : undefined}>
        <table className="data-table">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              {columns.map((column) => {
                const sortState = ariaSort(column);
                return (
                  <th
                    key={column.id}
                    scope="col"
                    aria-sort={column.sortValue ? sortState : undefined}
                    style={column.width ? { width: column.width } : undefined}
                    className={column.numeric ? 'cell-numeric' : undefined}
                  >
                    {column.sortValue ? (
                      <button type="button" className="sort-button" onClick={() => activate(column)}>
                        <span className="sort-button__text">{column.header}</span>
                        {sortState === 'ascending' ? (
                          <ArrowUp aria-hidden="true" />
                        ) : sortState === 'descending' ? (
                          <ArrowDown aria-hidden="true" />
                        ) : (
                          <ChevronsUpDown aria-hidden="true" />
                        )}
                        <span className="sr-only">
                          {sortState === 'ascending'
                            ? 'sorted ascending, activate to sort descending'
                            : sortState === 'descending'
                              ? 'sorted descending, activate to sort ascending'
                              : 'not sorted, activate to sort descending'}
                        </span>
                      </button>
                    ) : (
                      column.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr key={rowKey(row)} data-highlight={highlight?.(row) || undefined}>
                {columns.map((column, index) =>
                  index === 0 ? (
                    <th key={column.id} scope="row" className="cell-row-head">
                      {column.cell(row)}
                    </th>
                  ) : (
                    <td key={column.id} className={column.numeric ? 'cell-numeric' : undefined}>
                      {column.cell(row)}
                    </td>
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="record-list">
        {sorted.map((row) => (
          <li key={`card-${rowKey(row)}`} className="record-card" data-highlight={highlight?.(row) || undefined}>
            {renderCard(row)}
          </li>
        ))}
      </ul>

      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>
    </>
  );
}
