/**
 * Personalization — shows what the system has learned from feedback.
 *
 * Displays:
 *  1. Learning status (cold-start vs active)
 *  2. Per-model satisfaction estimates with confidence
 *  3. Feedback history
 *
 * All data comes from the backend — nothing is simulated.
 */
import { useCallback, useEffect, useState } from 'react';
import { Brain, RefreshCw, Star, ThumbsDown, ThumbsUp } from 'lucide-react';
import { PageHeader } from '../components/layout/PageHeader';
import { Card, CardBody, CardHeader } from '../components/ui/Card';
import { Panel, PanelBody } from '../components/ui/Panel';
import { Badge, Status, Tag } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { EmptyState, ErrorState } from '../components/ui/EmptyState';
import { LoadingIndicator } from '../components/ui/Skeleton';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { useAuth } from '../context/authContext';
import { getFeedback, getLearningState } from '../services/feedback.service';
import { describeError } from '../services/http';
import { OBJECTIVES } from '../utils/domain';
import { formatNumber, formatPercent, toPercent } from '../utils/format';
import type { FeedbackRecord, LearningState, ModelSatisfaction } from '../types';

export function Personalization() {
  useDocumentTitle('Personalization · AI Compass');
  const { user } = useAuth();

  const [learningState, setLearningState] = useState<LearningState | null>(null);
  const [history, setHistory] = useState<FeedbackRecord[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ message: string; hint?: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ls, fb] = await Promise.all([getLearningState(), getFeedback(50)]);
      setLearningState(ls);
      setHistory(fb);
    } catch (cause) {
      setError(describeError(cause, 'Could not load personalization data.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  return (
    <>
      <PageHeader
        eyebrow="Account"
        title="Personalization"
        description="AI Compass learns from your feedback to improve future routing decisions. Ratings are stored per model and used to nudge — not override — the objective routing scores."
        actions={
          <Button variant="secondary" size="sm" onClick={() => void load()} leadingIcon={<RefreshCw />}>
            Refresh
          </Button>
        }
      />

      <div className="page-body personalization-page-body">
        {loading ? (
          <Card><CardBody><LoadingIndicator label="Loading personalization data" /></CardBody></Card>
        ) : error ? (
          <ErrorState title="Could not load" message={error.message} hint={error.hint} onRetry={() => void load()} retryLabel="Try again" />
        ) : learningState ? (
          <div className="personalization-dashboard">
            <section className="personalization-overview" aria-label="Personalization overview">
              <div className="personalization-overview-state">
                <span className="personalization-learning-icon"><Brain aria-hidden="true" /></span>
                <div>
                  <p className="personalization-kicker">Learning profile</p>
                  <h2>{learningState.learning_active ? 'Learning is active' : 'Building your baseline'}</h2>
                  <p>{learningState.learning_active
                    ? 'Your feedback informs future recommendations alongside routing objectives.'
                    : 'Ratings build a per-model profile; routing priorities remain in control until enough feedback is available.'}</p>
                </div>
                <Status name={learningState.learning_active ? 'active' : 'warning'}>
                  {learningState.learning_active ? 'Active' : 'Cold start'}
                </Status>
              </div>
              <div className="personalization-metrics" aria-label="Feedback summary">
                <div><span>Total ratings</span><strong>{formatNumber(learningState.total_feedback, 0)}</strong></div>
                <div><span>Models rated</span><strong>{formatNumber(learningState.models_rated, 0)}</strong></div>
                <div><span>Activation</span><strong>{learningState.cold_start ? '3 ratings' : 'Reached'}</strong></div>
              </div>
            </section>

            {learningState.cold_start ? (
              <Panel tone="muted">
                <PanelBody>
                  <p className="personalization-next-step">
                    <Star aria-hidden="true" />
                    Rate a recommended model after a routing run. Personalization activates after at least 3 ratings.
                  </p>
                </PanelBody>
              </Panel>
            ) : null}

            <div className="personalization-analysis-grid">
              {user?.routing_preferences && (
                <Card className="personalization-priorities">
                  <CardHeader
                    title="Routing priorities"
                    compact
                    description="How your saved routing objectives are balanced."
                  />
                  <CardBody>
                    <div className="dimension-list">
                      {OBJECTIVES.map((objective) => (
                        <PreferenceRow
                          key={objective.key}
                          label={objective.label}
                          weight={user.routing_preferences[objective.key]}
                        />
                      ))}
                    </div>
                    <p className="panel-footnote personalization-footnote">
                      {user.preferences_customized
                        ? 'Your custom priorities are applied to future routing.'
                        : 'These saved defaults follow your user group.'}
                    </p>
                  </CardBody>
                </Card>
              )}

              <Card>
                <CardHeader
                  title="Learned model preferences"
                  compact
                  description="Satisfaction estimates from your ratings, with confidence shown per model."
                />
                <CardBody>
                  {learningState.satisfaction_estimates.length > 0 ? (
                    <>
                      <div className="personalization-satisfaction-list">
                        {learningState.satisfaction_estimates.map((est) => (
                          <SatisfactionRow key={est.model_id} est={est} />
                        ))}
                      </div>
                      <p className="panel-footnote personalization-footnote">
                        A Bayesian prior limits the impact of early ratings; learned preference influence is bounded.
                      </p>
                    </>
                  ) : (
                    <EmptyState
                      icon={<Brain />}
                      title="No learned preferences yet"
                      description="Rate models after routing tasks to build a preference ranking."
                    />
                  )}
                </CardBody>
              </Card>
            </div>

            <Card>
                <CardHeader
                  title="Feedback history"
                  compact
                  description="Ratings submitted after a recommendation, newest first."
                  actions={<Tag>{formatNumber(history?.length ?? 0, 0)} entries</Tag>}
                />
                <CardBody>
                  {!history || history.length === 0 ? (
                    <EmptyState
                      icon={<Star />}
                      title="Your model feedback starts here"
                      description="After routing a task, rate the recommended model. AI Compass uses those ratings to build a per-model preference profile."
                    />
                  ) : (
                    <div className="personalization-history">
                      {history.map((fb) => (
                        <FeedbackHistoryItem key={fb.feedback_id} fb={fb} />
                      ))}
                    </div>
                  )}
                </CardBody>
            </Card>
            <details className="personalization-method">
              <summary>How learning influences recommendations</summary>
              <p>Bayesian satisfaction estimates make a bounded adjustment to objective scores; they do not replace capability filtering or your routing priorities.</p>
            </details>
          </div>
        ) : null}
      </div>
    </>
  );
}

function PreferenceRow({ label, weight }: { label: string; weight: number }) {
  const percent = toPercent(weight);

  return (
    <div className="personalization-preference-row">
      <span className="dimension-label">{label}</span>
      <div
        className="satisfaction-bar-track"
        role="progressbar"
        aria-label={`${label} priority`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <div className="satisfaction-bar-fill" style={{ width: `${percent}%` }} />
      </div>
      <span className="personalization-preference-value">{formatPercent(weight, 0)}</span>
    </div>
  );
}

function SatisfactionRow({ est }: { est: ModelSatisfaction }) {
  const normalised = (est.mean_rating - 1) / 4; // 1–5 → 0–1
  const isPositive = normalised >= 0.5;
  const pct = Math.round(normalised * 100);

  return (
    <div className="satisfaction-bar personalization-satisfaction-row">
      <span className="mono personalization-model-id">
        {est.model_id}
      </span>
      <div className="satisfaction-bar-track">
        <div
          className={`satisfaction-bar-fill${isPositive ? '' : ' satisfaction-bar-fill--negative'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="personalization-rating">
        {est.mean_rating.toFixed(1)}★
      </span>
      <span className="personalization-samples">
        n={est.sample_count}
      </span>
      <span className="personalization-confidence">
        {formatPercent(est.confidence, 0)} conf.
      </span>
      <Status name={isPositive ? 'passed' : 'warning'}>
        {isPositive ? 'Preferred' : 'Avoided'}
      </Status>
    </div>
  );
}

function FeedbackHistoryItem({ fb }: { fb: FeedbackRecord }) {
  const stars = '★'.repeat(fb.rating) + '☆'.repeat(5 - fb.rating);
  return (
    <div className="feedback-history-item">
      <div className="feedback-history-meta">
        <span className="feedback-stars-display">{stars}</span>
        {fb.thumbs === 'up' ? <ThumbsUp size={12} /> : fb.thumbs === 'down' ? <ThumbsDown size={12} /> : null}
        <span className="mono personalization-history-model">{fb.model_name}</span>
        <Badge tone="neutral" outline>{fb.task_type}</Badge>
        <time dateTime={fb.created_at}>{new Date(fb.created_at).toLocaleDateString()}</time>
      </div>
      <p className="personalization-history-query">
        {fb.query_summary.slice(0, 120)}{fb.query_summary.length > 120 ? '…' : ''}
      </p>
      {fb.reasons.length > 0 ? (
        <div className="personalization-history-reasons">
          {fb.reasons.map((r) => <Tag key={r}>{r}</Tag>)}
        </div>
      ) : null}
      {fb.comment ? (
        <p className="personalization-history-comment">
          "{fb.comment}"
        </p>
      ) : null}
    </div>
  );
}
