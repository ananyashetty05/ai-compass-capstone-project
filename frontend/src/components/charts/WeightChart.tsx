/**
 * WeightChart — how the saved preferences became routing weights.
 *
 * Shows the weights the backend actually applied (`applied_weights`,
 * normalised to sum to 1), not the raw slider values, so the chart
 * matches the decision that was made.
 */
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ChartFrame } from './ChartFrame';
import { coerceNumber, formatPercent, humanizeToken } from '../../utils/format';
import { sum } from '../../utils/scores';

export interface WeightChartProps {
  title?: string;
  description?: string;
  weights: Record<string, number>;
  height?: number;
}

export function WeightChart({
  title = 'Applied routing weights',
  description = 'The relative importance of each objective after the backend normalised your saved preferences.',
  weights,
  height = 220,
}: WeightChartProps) {
  // A weight the backend did not report stays `null` so the bar renders
  // as absent rather than as a real zero-height bar. Sorting therefore
  // has to push those to the end — comparing them as `0` would
  // interleave "not reported" with genuine zero weights.
  const data = Object.entries(weights)
    .map(([key, value]) => ({ label: humanizeToken(key), value: typeof value === 'number' ? value : null }))
    .sort((a, b) => {
      if (a.value === null && b.value === null) return 0;
      if (a.value === null) return 1;
      if (b.value === null) return -1;
      return b.value - a.value;
    });

  // Missing weights contribute nothing to the total rather than counting
  // as zero, so the figure matches the bars that are actually drawn.
  const reported = data.filter((d): d is { label: string; value: number } => d.value !== null);
  const total = sum(reported.map((d) => d.value));
  const top = reported[0];

  return (
    <ChartFrame
      title={title}
      description={description}
      summary={
        top?.value
          ? `${top.label} carried the most weight at ${formatPercent(top.value)}${
              total !== null ? ` of a total of ${formatPercent(total)}` : ''
            }.`
          : undefined
      }
      series={['Weight']}
      data={data}
      format={(value) => formatPercent(value)}
      height={height}
      emptyMessage="The backend did not report applied weights for this result."
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
              domain={[0, 'auto']}
              tickFormatter={(value) => formatPercent(coerceNumber(value), 0)}
              stroke={theme.axis}
              tick={{ fill: theme.text, fontSize: 12 }}
              tickLine={false}
              width={48}
            />
            <Tooltip
              cursor={{ fill: theme.grid, opacity: 0.4 }}
              contentStyle={{
                background: theme.surface,
                border: '1px solid currentColor',
                borderRadius: 8,
                fontSize: 13,
              }}
              formatter={(value) => [formatPercent(coerceNumber(value), 1), 'Weight']}
            />
            <Bar dataKey="value" name="Weight" fill={theme.series[0]} radius={[4, 4, 0, 0]} maxBarSize={64} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartFrame>
  );
}
