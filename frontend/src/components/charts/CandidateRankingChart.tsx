/**
 * CandidateRankingChart — overall routing score per candidate model.
 *
 * Renders the scores the backend actually computed, in descending
 * order, with the selected model highlighted in the surrounding UI
 * rather than by a colour-only cue here.
 */
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ChartFrame } from './ChartFrame';
import { formatPercent, coerceNumber } from '../../utils/format';
import type { ModelScore } from '../../types';

export interface CandidateRankingChartProps {
  scores: readonly ModelScore[];
  selectedModelId: string;
  height?: number;
  /** Maximum number of candidates plotted. */
  limit?: number;
}

export function CandidateRankingChart({
  scores,
  selectedModelId,
  height = 280,
  limit = 10,
}: CandidateRankingChartProps) {
  const ranked = [...scores]
    .sort((a, b) => b.overall_score - a.overall_score)
    .slice(0, limit);

  const data = ranked.map((score) => ({
    label: score.model_id,
    value: score.overall_score,
    selected: score.model_id === selectedModelId,
  }));

  const selected = data.find((row) => row.selected);
  const runnerUp = data.filter((row) => !row.selected)[0];

  return (
    <ChartFrame
      title="Overall routing score by candidate"
      description="The weighted score the router computed for every surviving candidate, in descending order."
      summary={
        selected
          ? `${selected.label} ranked highest at ${formatPercent(selected.value)}${
              runnerUp ? `, ahead of ${runnerUp.label} at ${formatPercent(runnerUp.value)}` : ''
            }.`
          : undefined
      }
      series={['Overall score']}
      data={data}
      format={(value) => formatPercent(value)}
      height={height}
      emptyMessage="The backend did not return candidate scores for this run."
    >
      {(theme) => (
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} margin={{ top: 16, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid stroke={theme.grid} vertical={false} />
            <XAxis
              dataKey="label"
              stroke={theme.axis}
              tick={{ fill: theme.text, fontSize: 11 }}
              tickLine={false}
              interval={0}
              angle={-20}
              textAnchor="end"
              height={64}
            />
            <YAxis
              domain={[0, 1]}
              tickFormatter={(value: number) => formatPercent(value, 0)}
              stroke={theme.axis}
              tick={{ fill: theme.text, fontSize: 12 }}
              tickLine={false}
              width={48}
            />
            <Tooltip
              cursor={{ fill: theme.grid, opacity: 0.4 }}
              contentStyle={{ background: theme.surface, borderRadius: 8, fontSize: 13 }}
              formatter={(value) => [formatPercent(coerceNumber(value), 1), 'Overall score']}
            />
            <Bar dataKey="value" name="Overall score" radius={[4, 4, 0, 0]} maxBarSize={56}>
              {data.map((row) => (
                <Cell key={row.label} fill={row.selected ? theme.series[0] : theme.neutral} />
              ))}
              <LabelList
                dataKey="value"
                position="top"
                formatter={(value) => formatPercent(coerceNumber(value), 0)}
                fill={theme.text}
                fontSize={11}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartFrame>
  );
}
