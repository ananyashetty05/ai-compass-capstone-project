/**
 * Explanation.
 *
 * Reads the current session's routing result and shows how the decision
 * was reached: the query characteristics, the weights the router
 * applied, the per-model score breakdown, and the models that were
 * eliminated. Every value is taken from the payload the backend
 * returned — no score is recomputed here.
 *
 * Ordered by the questions a reader actually asks: what was decided and
 * why, what the query looked like, how the candidates compared, and
 * only then the arithmetic behind the winner.
 */
import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { BarChart3, BookOpen, Compass, FileSearch, Scale, Target, Workflow } from 'lucide-react';
import { PageHeader } from '../components/layout/PageHeader';
import { ButtonLink } from '../components/ui/Button';
import { ProvenanceTag, Status } from '../components/ui/Badge';
import { Card, CardBody, CardHeader } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import type { ColumnDef } from '../components/ui/DataTable';
import { DimensionRow } from '../components/ui/ScoreBar';
import { MetadataEntry, MetadataRow } from '../components/ui/Metadata';
import { Panel, PanelBody, PanelHeader } from '../components/ui/Panel';
import { Stat, StatStrip } from '../components/ui/MetricTile';
import { WeightChart } from '../components/charts/WeightChart';
import { QueryProfileChart } from '../components/charts/QueryProfileChart';
import { CandidateRankingChart } from '../components/charts/CandidateRankingChart';
import { EmptyState, Notice } from '../components/ui/EmptyState';
import { PIPELINE_STAGES, OBJECTIVE_KEYS, groupLabel } from '../utils/domain';
import { formatDuration, formatInteger, formatNumber, formatPercent, truncate } from '../utils/format';
import { useRouteResult } from '../context/routeResultContext';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import type { ModelScore } from '../types';

/**
 * The candidate table is the comparison; sorting it is more useful than
 * a fixed ranking, since the reader usually wants to sort by whichever
 * objective they care about. Every column is a pure function of the
 * score, so the set is built once at module scope.
 *
 * `secondary` columns are hidden on narrow viewports, keeping model,
 * quality and the overall winner visible.
 */
const SCORE_COLUMNS: ColumnDef<ModelScore>[] = [
  {
    id: 'model',
    header: 'Model',
    cell: (score) => <span className="cell-primary mono">{score.model_id}</span>,
    sortValue: (score) => score.model_id,
  },
  {
    id: 'quality',
    header: 'Quality',
    numeric: true,
    cell: (score) => <span className="text-numeric">{formatPercent(score.quality_score, 3)}</span>,
    sortValue: (score) => score.quality_score,
  },
  {
    id: 'cost',
    header: 'Cost',
    numeric: true,
    cell: (score) => <span className="text-numeric">{formatPercent(score.cost_score, 3)}</span>,
    sortValue: (score) => score.cost_score,
    secondary: true,
  },
  {
    id: 'latency',
    header: 'Latency',
    numeric: true,
    cell: (score) => <span className="text-numeric">{formatPercent(score.latency_score, 3)}</span>,
    sortValue: (score) => score.latency_score,
    secondary: true,
  },
  {
    id: 'reliability',
    header: 'Reliability',
    numeric: true,
    cell: (score) => <span className="text-numeric">{formatPercent(score.reliability_score, 3)}</span>,
    sortValue: (score) => score.reliability_score,
    secondary: true,
  },
  {
    id: 'risk',
    header: 'Risk',
    numeric: true,
    // Inverted so a higher value is safer, matching every other column.
    // The raw field is riskier-is-higher.
    cell: (score) => <span className="text-numeric">{formatPercent(1 - score.risk_score, 3)}</span>,
    sortValue: (score) => 1 - score.risk_score,
    secondary: true,
  },
  {
    id: 'alignment',
    header: 'Task-fit proxy',
    numeric: true,
    cell: (score) => <span className="text-numeric">{formatPercent(score.preference_alignment, 3)}</span>,
    sortValue: (score) => score.preference_alignment,
    secondary: true,
  },
  {
    id: 'overall',
    header: 'Overall',
    numeric: true,
    cell: (score) => <strong className="text-numeric">{formatPercent(score.overall_score, 3)}</strong>,
    sortValue: (score) => score.overall_score,
  },
];

export function Explanation() {
  useDocumentTitle('Explanation · AI Compass');
  const { result } = useRouteResult();

  const ranked = useMemo(() => {
    if (!result) return [];
    return [...result.model_scores].sort((a, b) => b.overall_score - a.overall_score);
  }, [result]);

  if (!result) {
    return (
      <div className="explanation-page">
        <PageHeader
          eyebrow="Decision"
          title="How the router decided"
          description="The full reasoning behind the current routing decision."
        />
        <Card>
          <CardBody>
            <EmptyState
              icon={<FileSearch />}
              title="No routing result to explain"
              description="Explanations are built from a completed routing run. Route a request first and the reasoning will appear here."
              action={
                <ButtonLink to="/route" variant="primary">
                  Route a request
                </ButtonLink>
              }
            />
          </CardBody>
        </Card>
      </div>
    );
  }

  const explanation = result.routing_explanation;
  const weights: Record<string, number> = explanation.applied_weights ?? {};
  const reasons = explanation.routing_reason ?? [];
  const selectedScore = result.model_scores.find((score) => score.model_id === result.selected_model_id) ?? null;
  const weightTotal = OBJECTIVE_KEYS.reduce(
    (sum, key) => sum + (typeof weights[key] === 'number' ? weights[key] : 0),
    0,
  );

  const columns: ColumnDef<ModelScore>[] = SCORE_COLUMNS;

  return (
    <div className="explanation-page">
      <PageHeader
        eyebrow="Decision"
        title="How the router decided"
        description={`Routing run for ${groupLabel(result.profile)}: ${truncate(result.query, 140)}`}
        actions={
          <ButtonLink to="/route" variant="secondary" size="sm">
            Route another query
          </ButtonLink>
        }
      />

      <div className="page-body">
        {/* 1. The decision itself, in the engine's own words */}
        {explanation.narrative ? (
          <Panel>
            <PanelHeader eyebrow="Summary" title="Why this model was selected" />
            <PanelBody>
              <p className="response-text">{explanation.narrative}</p>
            </PanelBody>
          </Panel>
        ) : null}

        {/* 2. The run at a glance */}
        <StatStrip label="Routing run">
          <Stat
            label="Selected"
            value={result.selected_model_name}
            source={result.selected_model_id}
          />
          <Stat
            label={result.escalation_info.escalated ? 'Final (escalated)' : 'Final model'}
            value={result.final_model_name}
            source={result.final_model_id}
          />
          <Stat
            label="Routing"
            value={formatDuration(result.performance_metrics.routing_latency_ms)}
            source="router time"
          />
          <Stat
            label="Total latency"
            value={formatDuration(result.performance_metrics.total_latency_ms)}
            source="end to end"
          />
          <Stat
            label="Scored"
            value={formatNumber(result.performance_metrics.candidates_evaluated ?? ranked.length, 0)}
            source="candidates"
          />
          <Stat
            label="Eliminated"
            value={formatNumber(result.performance_metrics.models_filtered ?? result.filtered_models.length, 0)}
            source="filtered out"
          />
        </StatStrip>

        {/* 3. What the query looked like, and the weights applied */}
        <div className="split">
          <Card>
            <CardHeader
              title="Applied weights"
              compact
              description={
                weightTotal > 0
                  ? 'The normalised weights the router scored with, derived from your saved preferences.'
                  : 'The router did not report applied weights for this run.'
              }
              icon={<Scale />}
              actions={<ProvenanceTag kind="estimated" label="Normalised by the router" />}
            />
            <CardBody>
              {Object.keys(weights).length > 0 ? (
                <WeightChart weights={weights} height={220} />
              ) : (
                <EmptyState
                  align="start"
                  icon={<Scale />}
                  title="Weights unavailable"
                  description="Your saved priorities were still applied server-side, but this payload did not include the resulting weight vector."
                />
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Query characteristics"
              compact
              description="Derived from your query text, before any model was considered."
              icon={<Target />}
              actions={<ProvenanceTag kind="estimated" label={result.query_analysis.analysis_method} />}
            />
            <CardBody>
              <QueryProfileChart profile={result.query_analysis} height={220} />
            </CardBody>
          </Card>
        </div>

        {/* 4. The comparison, as a sortable table rather than a chart */}
        <section className="page-section">
          <div className="section-header">
            <div>
              <h3 className="section-title">Candidate scores</h3>
              <p className="section-subtitle">
                Every model the router scored. Risk is shown inverted so a higher value is safer; overall is the
                weighted score, not an average of the columns.
              </p>
            </div>
          </div>

          <div className="table-surface">
            <div className="table-toolbar">
              <span className="toolbar-label">Ranked by overall score</span>
              <p className="toolbar-count">{formatInteger(ranked.length)} candidates</p>
            </div>
            <DataTable
              flush
              caption="Every candidate model with each sub-score and its overall routing score"
              columns={columns}
              rows={ranked}
              rowKey={(score) => score.model_id}
              initialSort={{ columnId: 'overall', direction: 'desc' }}
              highlight={(score) => score.model_id === result.selected_model_id}
              renderCard={(score) => (
                <div>
                  <div className="record-head">
                    <div>
                      <p className="record-title mono">{score.model_id}</p>
                      <p className="record-subtitle">
                        Overall {formatPercent(score.overall_score, 3)}
                      </p>
                    </div>
                    {score.model_id === result.selected_model_id ? (
                      <Status name="selected">Selected</Status>
                    ) : score.model_id === result.escalation_info.fallback_model_id ? (
                      <Status name="escalated">Escalation target</Status>
                    ) : null}
                  </div>
                  <dl className="record-metrics">
                    <div className="record-metric">
                      <dt className="record-metric-label">Quality</dt>
                      <dd className="record-metric-value">{formatPercent(score.quality_score, 3)}</dd>
                    </div>
                    <div className="record-metric">
                      <dt className="record-metric-label">Cost</dt>
                      <dd className="record-metric-value">{formatPercent(score.cost_score, 3)}</dd>
                    </div>
                    <div className="record-metric">
                      <dt className="record-metric-label">Latency</dt>
                      <dd className="record-metric-value">{formatPercent(score.latency_score, 3)}</dd>
                    </div>
                    <div className="record-metric">
                      <dt className="record-metric-label">Reliability</dt>
                      <dd className="record-metric-value">{formatPercent(score.reliability_score, 3)}</dd>
                    </div>
                    <div className="record-metric">
                      <dt className="record-metric-label">Risk</dt>
                      <dd className="record-metric-value">{formatPercent(1 - score.risk_score, 3)}</dd>
                    </div>
                    <div className="record-metric">
                      <dt className="record-metric-label">Task-fit proxy</dt>
                      <dd className="record-metric-value">{formatPercent(score.preference_alignment, 3)}</dd>
                    </div>
                  </dl>
                </div>
              )}
              emptyState={
                <EmptyState
                  title="No candidate scores were returned"
                  description="The routing payload did not include a score row for any model, so there is nothing to compare."
                />
              }
            />
          </div>

          <details className="disclosure">
            <summary>
              <BarChart3 aria-hidden="true" />
              Ranking chart
            </summary>
            <div className="disclosure-body">
              <CandidateRankingChart
                scores={result.model_scores}
                selectedModelId={result.selected_model_id}
                height={280}
              />
            </div>
          </details>
        </section>

        {/* 5. The arithmetic behind the winner */}
        <div className="split">
          {selectedScore ? (
            <Card>
              <CardHeader
                title="Score detail"
                compact
                description={`The sub-scores and weighted total for ${result.selected_model_name}.`}
                icon={<BookOpen />}
              />
              <CardBody>
                <div className="dimension-list">
                  <DimensionRow label="Quality" value={selectedScore.quality_score} />
                  <DimensionRow label="Cost efficiency" value={selectedScore.cost_score} />
                  <DimensionRow label="Latency" value={selectedScore.latency_score} />
                  <DimensionRow label="Reliability" value={selectedScore.reliability_score} />
                  <DimensionRow
                    label="Risk"
                    value={1 - selectedScore.risk_score}
                    description="Inverted so that higher is safer."
                  />
                  <DimensionRow label="Task/capability-fit proxy" value={selectedScore.preference_alignment} description="This score estimates query-to-model task/domain fit; it is not a validated semantic measure of personal preference." />
                </div>
                <p className="panel-note">
                  Research limitation: the fit proxy is derived from query characteristics and model capabilities.
                  It should not be interpreted as a validated measure of individual preference alignment.
                </p>
                {selectedScore.score_breakdown ? (
                  <details className="disclosure">
                    <summary>
                      <FileSearch aria-hidden="true" />
                      Full score breakdown
                    </summary>
                    <div className="disclosure-body">
                      <MetadataRow label="Full score breakdown" columns="2">
                        {Object.entries(selectedScore.score_breakdown).map(([key, value]) => (
                          <MetadataEntry key={key} label={key.replace(/_/g, ' ')} value={formatPercent(value, 3)} />
                        ))}
                      </MetadataRow>
                    </div>
                  </details>
                ) : null}
              </CardBody>
            </Card>
          ) : null}

          <Card>
            <CardHeader
              title="Eliminated candidates"
              compact
              description={`${formatNumber(result.filtered_models.length, 0)} model${
                result.filtered_models.length === 1 ? '' : 's'
              } removed before scoring.`}
            />
            <CardBody>
              {result.filtered_models.length > 0 ? (
                <ul className="elimination-list">
                  {result.filtered_models.map((filtered) => (
                    <li key={filtered.model_id} className="elimination-item">
                      <span className="elimination-model mono">{filtered.model_id}</span>
                      <span className="elimination-reason">{filtered.reason}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  align="start"
                  title="Nothing was eliminated"
                  description="Every active model in the registry was eligible, so no model was removed by filtering."
                />
              )}
            </CardBody>
          </Card>
        </div>

        {/* 6. The engine's stated reasons */}
        {reasons.length > 0 ? (
          <Card>
            <CardHeader
              title="Why this model"
              compact
              description="The reasons the router reported for its selection."
            />
            <CardBody>
              <ol className="reason-list">
                {reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ol>
            </CardBody>
          </Card>
        ) : null}

        {/* 7. The pipeline, collapsed — reference rather than narrative */}
        <details className="disclosure">
          <summary>
            <Workflow aria-hidden="true" />
            Pipeline executed
          </summary>
          <div className="disclosure-body">
            <ol className="pipeline pipeline-compact">
              {PIPELINE_STAGES.map((stage) => (
                <li key={stage.id} className="pipeline-step" data-state="done">
                  <span className="pipeline-marker" aria-hidden="true" />
                  <span className="pipeline-title">{stage.label}</span>
                  <span className="pipeline-detail">{stage.detail}</span>
                </li>
              ))}
            </ol>
          </div>
        </details>

        <Notice tone="info" title="How to read this">
          Scores are computed from registry metadata, not from live benchmarks. A higher overall score means the model
          fit your saved priorities better <em>for this query</em>, not that it is better in general. The same weights
          will produce a different ranking for a different query.
        </Notice>

        <div className="row row-wrap">
          <ButtonLink to="/evaluation" variant="secondary" size="sm" leadingIcon={<Compass />}>
            Compare routing strategies
          </ButtonLink>
          <ButtonLink to="/models" variant="ghost" size="sm">
            Inspect the registry
          </ButtonLink>
          <Link to="/profile" className="text-link">
            Change your priorities
          </Link>
        </div>
      </div>
    </div>
  );
}
