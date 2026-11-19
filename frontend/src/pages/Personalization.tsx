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
import { ArrowRight, Brain, RefreshCw, SlidersHorizontal, Star, ThumbsDown, ThumbsUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Grid, PropertyList, SectionHeader, Stat, StatusPill, Surface } from '../components/ui/ds';
import { PageHeader } from '../components/layout/PageHeader';
import { Card, CardBody } from '../components/ui/Card';
import { Badge, Status, Tag } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { EmptyState, ErrorState } from '../components/ui/EmptyState';
import { Radar } from '../components/ui/Radar';
import { LoadingIndicator } from '../components/ui/Skeleton';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { useAsync } from '../hooks/useAsync';
import { useAuth } from '../context/authContext';
import { getFeedback, getLearningState } from '../services/feedback.service';
import { OBJECTIVES, groupLabel } from '../utils/domain';
import { formatNumber, formatPercent, toPercent } from '../utils/format';
import type { FeedbackRecord, ModelSatisfaction } from '../types';

const ACTIVATION_RATINGS = 3;

export function Personalization() {
  useDocumentTitle('Personalization · AI Compass');
  const { user } = useAuth();
  const personalization = useAsync(async (signal) => {
    const [learningState, history] = await Promise.all([
      getLearningState(signal),
      getFeedback(50, signal),
    ]);
    return { learningState, history };
  }, []);
  const { learningState, history } = personalization.data ?? {};
  const averageRating = history && history.length > 0 ? history.reduce((sum, item) => sum + item.rating, 0) / history.length : null;

  return (
    <>
      <PageHeader
        eyebrow="Account"
        title="Personalization"
        description="AI Compass learns from your feedback to improve future routing decisions. Ratings are stored per model and used to nudge — not override — the objective routing scores."
        actions={
          <Button variant="secondary" size="sm" onClick={personalization.reload} leadingIcon={<RefreshCw />}>
            Refresh
          </Button>
        }
      />

      <div className="page-body personalization-page-body">
        {personalization.isLoading ? (
          <Card><CardBody><LoadingIndicator label="Loading personalization data" /></CardBody></Card>
        ) : personalization.error ? (
          <ErrorState title="Could not load" message={personalization.error.message} hint={personalization.error.hint} onRetry={personalization.reload} retryLabel="Try again" />
        ) : learningState ? (
          <div className="pz">
            <Surface className="pz-hero" aria-label="Learning status">
              <div className="pz-hero-main">
                <span className="personalization-learning-icon"><Brain aria-hidden="true" /></span>
                <div>
                  <p className="ds-kicker">Learning profile</p>
                  <h2>{learningState.learning_active ? 'Learning is active' : 'Building your baseline'}</h2>
                  <p className="pz-muted">{learningState.learning_active
                    ? 'Your feedback informs future recommendations alongside routing objectives.'
                    : 'Ratings build a per-model profile; routing priorities stay in control until enough feedback is available.'}</p>
                </div>
                <StatusPill tone={learningState.learning_active ? 'success' : 'warning'}>
                  {learningState.learning_active ? 'Active' : 'Cold start'}
                </StatusPill>
              </div>
              <Grid cols={3} className="pz-stats">
                <Stat label="Total ratings" value={formatNumber(learningState.total_feedback, 0)} />
                <Stat label="Models rated" value={formatNumber(learningState.models_rated, 0)} />
                <Stat label="Activation" value={learningState.cold_start ? `${ACTIVATION_RATINGS} ratings` : 'Reached'}
                  hint={averageRating !== null ? `Average given: ${averageRating.toFixed(1)}★` : undefined} />
              </Grid>
              <div className="cx-progress" role="progressbar" aria-label="Ratings toward activation" aria-valuemin={0} aria-valuemax={ACTIVATION_RATINGS} aria-valuenow={Math.min(learningState.total_feedback, ACTIVATION_RATINGS)}>
                <span style={{ ['--w' as string]: `${Math.min(100, (learningState.total_feedback / ACTIVATION_RATINGS) * 100)}%` }} />
              </div>
              <p className="pz-muted">
                {learningState.cold_start
                  ? `${learningState.total_feedback} of ${ACTIVATION_RATINGS} ratings needed. Rate a recommended model after a routing run to start personalization.`
                  : `Active with ${learningState.total_feedback} rating${learningState.total_feedback === 1 ? '' : 's'} across ${learningState.models_rated} model${learningState.models_rated === 1 ? '' : 's'}.`}
              </p>
            </Surface>

            <Grid ratio="1-2" className="pz-main">
              {user?.routing_preferences ? (
                <Surface className="pz-card" aria-labelledby="pz-priorities">
                  <SectionHeader id="pz-priorities" kicker="Configured by you" title="Routing priorities"
                    actions={<Link to="/profile" className="cx-link"><SlidersHorizontal aria-hidden="true" /> Edit <ArrowRight aria-hidden="true" /></Link>} />
                  <PropertyList items={[
                    { label: 'Name', value: user.name ?? 'Not set' },
                    { label: 'User group', value: groupLabel(user.user_group) },
                    { label: 'Priorities', value: user.preferences_customized ? 'Custom weights' : 'Group defaults' },
                  ]} />
                  <Radar label="Your routing priorities" size={300} axes={OBJECTIVES.map((o) => { const w = user.routing_preferences[o.key]; return { label: o.shortLabel, value: typeof w === 'number' ? w : null, display: typeof w === 'number' ? formatPercent(w, 0) : 'n/a' }; })} />
                  <div className="dimension-list">
                    {OBJECTIVES.map((objective) => (
                      <PreferenceRow key={objective.key} label={objective.label} description={objective.description} weight={user.routing_preferences[objective.key]} />
                    ))}
                  </div>
                </Surface>
              ) : null}

              <Surface className="pz-card" aria-labelledby="pz-learned">
                <SectionHeader id="pz-learned" kicker="Learned from feedback" title="Learned model preferences"
                  description="Satisfaction estimates from your ratings, with confidence per model." />
                {learningState.satisfaction_estimates.length > 0 ? (
                  <>
                    <div className="personalization-satisfaction-list">
                      {learningState.satisfaction_estimates.map((est) => <SatisfactionRow key={est.model_id} est={est} />)}
                    </div>
                    <p className="pz-muted">A Bayesian prior limits the impact of early ratings; learned preference influence is bounded and never replaces capability filtering or your priorities.</p>
                  </>
                ) : (
                  <EmptyState icon={<Brain />} title="No learned preferences yet" description="Rate models after routing tasks to build a preference ranking." align="start" />
                )}
              </Surface>
            </Grid>

            <Surface className="pz-card" aria-labelledby="pz-history">
              <SectionHeader id="pz-history" kicker="Activity" title="Feedback history"
                description="Ratings submitted after a recommendation, newest first." actions={<Tag>{formatNumber(history?.length ?? 0, 0)} entries</Tag>} />
              {!history || history.length === 0 ? (
                <EmptyState icon={<Star />} title="Your model feedback starts here"
                  description="After routing a task, rate the recommended model. AI Compass uses those ratings to build a per-model preference profile." align="start" />
              ) : (
                <div className="personalization-history pz-history-grid">
                  {history.map((fb) => <FeedbackHistoryItem key={fb.feedback_id} fb={fb} />)}
                </div>
              )}
            </Surface>
          </div>
        ) : null}
      </div>
    </>
  );
}

function PreferenceRow({ label, weight, description }: { label: string; weight: number; description?: string }) {
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
      {description ? <p className="cx-pref-help">A higher weight favours models that score well on this. {description}</p> : null}
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
