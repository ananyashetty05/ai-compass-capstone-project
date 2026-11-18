import { AlertTriangle, ArrowRight, CheckCircle2, Info, ShieldAlert } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Reveal } from '../ui/Reveal';
import type { AttentionItem } from './insights';

const ICON = { warning: AlertTriangle, danger: ShieldAlert, info: Info };

export function AttentionCard({ items, loading }: { items: AttentionItem[]; loading: boolean }) {
  return (
    <Reveal as="section" className="cx-card" ariaLabelledBy="attn-title">
      <header className="cx-card-head">
        <div><p className="cx-kicker">System</p><h2 id="attn-title">Needs attention</h2></div>
        {items.length > 0 ? <span className="cx-count" aria-label={`${items.length} items`}>{items.length}</span> : null}
      </header>
      {loading ? (
        <p className="cx-muted" role="status">Checking the environment…</p>
      ) : items.length === 0 ? (
        <div className="cx-allgood"><CheckCircle2 aria-hidden="true" /><div><strong>Nothing needs attention</strong><span>Health, providers and registry reported no issues.</span></div></div>
      ) : (
        <ul className="cx-attn">
          {items.map((item) => {
            const Icon = ICON[item.tone];
            return (
              <li key={item.id} data-tone={item.tone}>
                <span className="cx-attn-icon" aria-hidden="true"><Icon /></span>
                <div>
                  <strong>{item.title}</strong>
                  <span>{item.detail}</span>
                  {item.to ? <Link to={item.to} className="cx-link">{item.action ?? 'Open'} <ArrowRight aria-hidden="true" /></Link> : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Reveal>
  );
}
