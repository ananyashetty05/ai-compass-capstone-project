/**
 * QueryProfileChart — the requirements the backend detected in a query.
 *
 * The detected characteristics drive candidate filtering and scoring, so
 * they are surfaced rather than hidden behind the decision.
 */
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ChartFrame } from './ChartFrame';
import { coerceNumber, formatNumber, formatPercent } from '../../utils/format';
import { humanizeToken } from '../../utils/format';
import type { QueryProfile } from '../../types';

/** Requirement dimensions that are scored between 0 and 1. */
const REQUIREMENTS: { key: keyof QueryProfile; label: string }[] = [
  { key: 'complexity', label: 'Complexity' },
  { key: 'quality_requirement', label: 'Quality' },
  { key: 'risk_level', label: 'Risk' },
  { key: 'latency_requirement', label: 'Speed' },
  { key: 'cost_sensitivity', label: 'Cost sensitivity' },
  { key: 'reliability_requirement', label: 'Reliability' },
  { key: 'context_requirement', label: 'Context' },
];

export interface QueryProfileChartProps {
  profile: QueryProfile;
  height?: number;
}

export function QueryProfileChart({ profile, height = 240 }: QueryProfileChartProps) {
  const data = REQUIREMENTS.map(({ key, label }) => {
    const raw = profile[key];
    return { label, value: typeof raw === 'number' ? raw : null };
  });

  return (
    <ChartFrame
      title="Detected query requirements"
      description="Each requirement is derived from the query text and influences which models survive filtering and how they are scored."
      summary={`Classified as ${humanizeToken(profile.task_type)} in ${humanizeToken(profile.domain)}, with an estimated ${formatNumber(profile.estimated_tokens, 0)} tokens.`}
      series={['Requirement']}
      data={data}
      format={(value) => formatPercent(value)}
      height={height}
      emptyMessage="The backend did not report query characteristics for this run."
    >
      {(theme) => (
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
            <CartesianGrid stroke={theme.grid} vertical={false} />
            <XAxis
              dataKey="label"
              stroke={theme.axis}
              tick={{ fill: theme.text, fontSize: 12 }}
              tickLine={false}
              interval={0}
            />
            <YAxis
              domain={[0, 1]}
              tickFormatter={(value) => formatPercent(coerceNumber(value), 0)}
              stroke={theme.axis}
              tick={{ fill: theme.text, fontSize: 12 }}
              tickLine={false}
              width={48}
            />
            <Tooltip
              cursor={{ fill: theme.grid, opacity: 0.4 }}
              contentStyle={{ background: theme.surface, borderRadius: 8, fontSize: 13 }}
              formatter={(value) => [formatPercent(coerceNumber(value), 1), 'Requirement']}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="value" name="Requirement" fill={theme.series[0]} radius={[4, 4, 0, 0]} maxBarSize={48} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartFrame>
  );
}
