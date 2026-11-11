/**
 * ScoreComparisonChart — grouped horizontal bars for the six routing
 * dimensions of one or more models.
 *
 * Accessibility: the SVG is exposed as a single labelled image and the
 * full data set is always available as a table via `ChartFrame`.
 */
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, XAxis, YAxis } from 'recharts';
import { ChartFrame } from './ChartFrame';
import { formatPercent } from '../../utils/format';

export interface ScoreDatum {
  label: string;
  [series: string]: string | number | null;
}

export interface ScoreComparisonChartProps {
  title: string;
  description?: string;
  summary?: string;
  data: ScoreDatum[];
  /** Series keys in display order; must exist on every datum. */
  series: string[];
  height?: number;
}

export function ScoreComparisonChart({ title, description, summary, data, series, height }: ScoreComparisonChartProps) {
  return (
    <ChartFrame
      title={title}
      description={description}
      summary={summary}
      series={series}
      data={data.map((datum) => ({
        label: datum.label,
        // The first series drives the canvas; every series reaches the
        // table alternative so no dimension is visual-only.
        value: typeof datum[series[0]] === 'number' ? (datum[series[0]] as number) : null,
        values: series.map((key) => (typeof datum[key] === 'number' ? (datum[key] as number) : null)),
      }))}
      format={(value) => formatPercent(value)}
      height={height}
      emptyMessage="No routing scores are available for this result."
    >
      {(theme, barId) => (
        <ResponsiveContainer width="100%" height={height ?? 260}>
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }} barGap={2}>
            <CartesianGrid stroke={theme.grid} horizontal={false} />
            <XAxis
              type="number"
              domain={[0, 1]}
              tickFormatter={(value: number) => formatPercent(value, 0)}
              stroke={theme.axis}
              tick={{ fill: theme.text, fontSize: 12 }}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="label"
              width={124}
              stroke={theme.axis}
              tick={{ fill: theme.text, fontSize: 12 }}
              tickLine={false}
            />
            {series.map((key, index) => (
              <Bar
                key={key}
                id={index === 0 ? barId : undefined}
                dataKey={key}
                name={key}
                fill={theme.series[index % theme.series.length]}
                radius={index === series.length - 1 ? [0, 4, 4, 0] : 0}
                maxBarSize={22}
              >
                {data.map((datum) => (
                  <Cell key={String(datum.label)} fill={theme.series[index % theme.series.length]} />
                ))}
              </Bar>
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartFrame>
  );
}
