/**
 * Approved ecosystem overview for the Model Pool. One card per category, each a working filter button.
 * Primary counts are exclusive and add up to the pool total; "also serves" counts overlap by design
 * (a product documented for two categories is compared in both) and are never summed.
 */
import { Boxes, Code2, FileText, Film, Image as ImageIcon, MessageSquare, Music2, Plug, X } from 'lucide-react';
import type { ComponentType } from 'react';
import type { EcosystemCategory, PoolStats } from '../../types';

export type EcoFilter = 'all' | EcosystemCategory;

const ICON: Record<EcosystemCategory, ComponentType<{ 'aria-hidden'?: boolean }>> = {
  conversational: MessageSquare, image: ImageIcon, video: Film, music_voice: Music2, document_design: FileText, api_models: Plug, coding: Code2,
};

export function ApprovedEcosystem({ stats, selected, onSelect }: { stats: PoolStats; selected: EcoFilter; onSelect: (next: EcoFilter) => void }) {
  const cats = stats.ecosystem?.categories ?? [];
  if (!cats.length) return null;
  const cap = stats.cap ?? 50;
  const sum = cats.map((c) => c.primary_count);
  const active = cats.find((c) => c.id === selected);
  return (
    <section className="ae" aria-labelledby="ae-title">
      <header className="ae-head">
        <div>
          <p className="ds-kicker">Approved ecosystem</p>
          <h2 id="ae-title">{stats.pool_total} products across {cats.length} categories</h2>
          <p className="ae-sub">The only products AI Compass compares. Cap {cap}. Pick a category to filter the list below; the router compares within one category at a time.</p>
        </div>
        <div className="ae-meter" aria-label={`${stats.pool_total} of ${cap} slots used`}>
          <span><b>{stats.pool_total}</b> / {cap}</span>
          <i><u style={{ width: `${Math.min(100, (stats.pool_total / cap) * 100)}%` }} /></i>
        </div>
      </header>
      <div className="ae-grid" role="group" aria-label="Filter by category">
        <button type="button" className="ae-card ae-card--all" aria-pressed={selected === 'all'} onClick={() => onSelect('all')}>
          <span className="ae-ico"><Boxes aria-hidden /></span>
          <span className="ae-name">All categories</span>
          <span className="ae-count">{stats.pool_total}</span>
          <span className="ae-note">{sum.join(' + ')} = {stats.pool_total}</span>
        </button>
        {cats.map((c, i) => {
          const Icon = ICON[c.id];
          const extra = c.serving_count - c.primary_count;
          return (
            <button type="button" key={c.id} className="ae-card" style={{ animationDelay: `${i * 45}ms` }} aria-pressed={selected === c.id} onClick={() => onSelect(selected === c.id ? 'all' : c.id)}>
              <span className="ae-ico"><Icon aria-hidden /></span>
              <span className="ae-name">{c.label}</span>
              <span className="ae-count">{c.primary_count}</span>
              <span className="ae-note">{extra > 0 ? `+${extra} also serve it · ${c.serving_count} compared` : 'products'}</span>
              <span className="ae-members">{c.members.filter((m) => m.role === 'primary').slice(0, 4).map((m) => m.model_name).join(' · ')}{c.primary_count > 4 ? ' …' : ''}</span>
            </button>
          );
        })}
      </div>
      {active ? (
        <p className="ae-active" role="status">
          Showing {active.serving_count} product{active.serving_count === 1 ? '' : 's'} compared for {active.label}.
          <button type="button" onClick={() => onSelect('all')}><X aria-hidden />Clear</button>
        </p>
      ) : null}
    </section>
  );
}
