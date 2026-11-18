import type { ReactNode } from 'react';
import { Activity, Database, KeyRound, Route } from 'lucide-react';
import { CountUp } from '../ui/CountUp';
import { Reveal } from '../ui/Reveal';
import { UNAVAILABLE } from '../../types';

export interface Kpi {
  id: string;
  label: string;
  icon: ReactNode;
  /** null → "Unavailable". Never a stand-in zero. */
  value: number | null;
  /** Shown instead of a number (e.g. a relative time). */
  text?: string | null;
  of?: number | null;
  detail: ReactNode;
  tone?: 'default' | 'good' | 'warn';
  loading?: boolean;
}

export function KpiCard({ kpi, index }: { kpi: Kpi; index: number }) {
  return (
    <Reveal as="div" className="cx-kpi" delay={index} >
      <p className="cx-kpi-label"><span aria-hidden="true" className="cx-kpi-icon">{kpi.icon}</span>{kpi.label}</p>
      <p className="cx-kpi-value" data-unavailable={kpi.value === null && !kpi.text && !kpi.loading ? 'true' : undefined} data-tone={kpi.tone}>
        {kpi.loading ? <span className="cx-skel" aria-label="Loading" /> : kpi.text ? <span className="cx-kpi-text">{kpi.text}</span> : kpi.value === null ? UNAVAILABLE : <CountUp value={kpi.value} />}
        {!kpi.loading && kpi.value !== null && typeof kpi.of === 'number' ? <span className="cx-kpi-of"> / {kpi.of}</span> : null}
      </p>
      <p className="cx-kpi-detail">{kpi.detail}</p>
    </Reveal>
  );
}

export function KpiRow({ kpis }: { kpis: Kpi[] }) {
  return (
    <section className="cx-kpis" aria-label="Key figures">
      {kpis.map((kpi, i) => <KpiCard key={kpi.id} kpi={kpi} index={i} />)}
    </section>
  );
}

export const KpiIcons = { models: <Database />, providers: <KeyRound />, routing: <Route />, registry: <Activity /> };
