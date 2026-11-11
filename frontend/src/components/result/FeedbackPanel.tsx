/**
 * FeedbackPanel — collect user feedback after a routing run.
 *
 * Submits to POST /api/v1/feedback. Shows a compact success state after
 * submission. Feedback is persisted and used to personalise future routing.
 */
import { useCallback, useState } from 'react';
import { Check, ThumbsDown, ThumbsUp } from 'lucide-react';
import { Panel, PanelBody, PanelHeader } from '../ui/Panel';
import { Button } from '../ui/Button';
import { Tag } from '../ui/Badge';
import { useToast } from '../../context/toastContext';
import { submitFeedback } from '../../services/feedback.service';
import { describeError } from '../../services/http';
import type { RouteResponse } from '../../types';

const REASON_OPTIONS = [
  'Accurate answer',
  'Clear explanation',
  'Good code quality',
  'Fast response',
  'Wrong answer',
  'Incomplete response',
  'Too verbose',
  'Off-topic',
  'Poor code quality',
  'Slow response',
];

interface Props {
  result: RouteResponse;
}

type SubmitState = 'idle' | 'submitting' | 'done' | 'error';

export function FeedbackPanel({ result }: Props) {
  const { push } = useToast();
  const [rating, setRating] = useState<number | null>(null);
  const [thumbs, setThumbs] = useState<'up' | 'down' | null>(null);
  const [reasons, setReasons] = useState<string[]>([]);
  const [comment, setComment] = useState('');
  const [state, setState] = useState<SubmitState>('idle');

  const toggleReason = useCallback((r: string) => {
    setReasons((prev) => (prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r]));
  }, []);

  const submit = useCallback(async () => {
    if (!rating || state === 'submitting') return;
    setState('submitting');
    try {
      await submitFeedback({
        routing_id: result.routing_id ?? 'unknown',
        model_id: result.final_model_id,
        model_name: result.final_model_name,
        query_summary: result.query.slice(0, 300),
        task_type: result.query_analysis.task_type,
        domain: result.query_analysis.domain,
        rating,
        thumbs,
        reasons,
        comment: comment.trim() || null,
      });
      setState('done');
      push({
        tone: 'success',
        title: 'Feedback saved',
        description: 'Thank you — this improves future routing decisions.',
      });
    } catch (cause) {
      setState('error');
      push({ tone: 'danger', title: 'Could not save feedback', description: describeError(cause).message });
    }
  }, [rating, thumbs, reasons, comment, result, state, push]);

  if (state === 'done') {
    return (
      <Panel tone="muted">
        <PanelBody>
          <div className="feedback-done">
            <Check aria-hidden="true" />
            <span>Feedback saved — routing will adapt over time.</span>
          </div>
        </PanelBody>
      </Panel>
    );
  }

  return (
    <Panel>
      <PanelHeader eyebrow="Personalisation" title="Rate this response" />
      <PanelBody>
        {/* Thumbs */}
        <div className="feedback-thumbs">
          <Button
            size="sm"
            variant={thumbs === 'up' ? 'primary' : 'secondary'}
            onClick={() => {
              setThumbs(thumbs === 'up' ? null : 'up');
              if (!rating) setRating(4);
            }}
            leadingIcon={<ThumbsUp />}
          >
            Helpful
          </Button>
          <Button
            size="sm"
            variant={thumbs === 'down' ? 'primary' : 'secondary'}
            onClick={() => {
              setThumbs(thumbs === 'down' ? null : 'down');
              if (!rating) setRating(2);
            }}
            leadingIcon={<ThumbsDown />}
          >
            Not helpful
          </Button>
        </div>

        {/* Star rating */}
        <div className="feedback-stars" role="group" aria-label="Star rating">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              className={`star-btn${rating !== null && n <= rating ? ' star-btn--active' : ''}`}
              onClick={() => setRating(n)}
              aria-label={`${n} star${n === 1 ? '' : 's'}`}
            >
              ★
            </button>
          ))}
          {rating ? <span className="feedback-rating-label">{rating} / 5</span> : null}
        </div>

        {/* Reason tags */}
        <div className="feedback-reasons">
          <p className="feedback-reasons-label">What stood out? (optional)</p>
          <div className="feedback-reason-tags">
            {REASON_OPTIONS.map((r) => (
              <button
                key={r}
                type="button"
                className={`reason-tag${reasons.includes(r) ? ' reason-tag--active' : ''}`}
                onClick={() => toggleReason(r)}
              >
                {r}
              </button>
            ))}
          </div>
        </div>

        {/* Comment */}
        <div className="field">
          <label className="field-label" htmlFor="feedback-comment">
            Comment (optional)
          </label>
          <textarea
            id="feedback-comment"
            className="input"
            rows={2}
            maxLength={1000}
            placeholder="Anything else about this response…"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>

        <div className="row">
          <Button
            variant="primary"
            size="sm"
            onClick={() => void submit()}
            loading={state === 'submitting'}
            disabled={!rating}
          >
            Submit feedback
          </Button>
          {state === 'error' ? <Tag>Failed to save — try again</Tag> : null}
        </div>

        <p className="panel-footnote">
          Your rating personalises future routing decisions for your account.
          {result.learning_active
            ? ' Personalised routing is currently active.'
            : ' Routing will adapt after a few ratings.'}
        </p>
      </PanelBody>
    </Panel>
  );
}
