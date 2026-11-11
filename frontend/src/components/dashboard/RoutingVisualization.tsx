import { Bot, Compass, MessageSquareText, Sparkles } from 'lucide-react';

export function RoutingVisualization() {
  return (
    <figure className="routing-visualization" aria-label="Illustration of a query moving through AI Compass to a recommended model">
      <svg className="routing-flow-lines" viewBox="0 0 640 220" preserveAspectRatio="none" aria-hidden="true">
        <path className="routing-flow-track" d="M145 110 C190 110 235 110 280 110" />
        <path className="routing-flow-track" d="M360 110 C405 110 450 110 495 110" />
        <path className="routing-flow-line" d="M145 110 C190 110 235 110 280 110" />
        <path className="routing-flow-line" d="M360 110 C405 110 450 110 495 110" />
        <circle className="routing-particle" r="3.5">
          <animateMotion dur="5.6s" repeatCount="indefinite" path="M145 110 C190 110 235 110 280 110" />
        </circle>
        <circle className="routing-particle routing-particle-late" r="3.5">
          <animateMotion dur="5.6s" repeatCount="indefinite" path="M360 110 C405 110 450 110 495 110" />
        </circle>
      </svg>

      <div className="routing-flow-node routing-query-node">
        <span className="routing-node-icon"><MessageSquareText aria-hidden="true" /></span>
        <span className="routing-node-label">Your query</span>
        <span className="routing-node-detail">Task and intent</span>
      </div>

      <div className="routing-flow-node routing-engine-node">
        <span className="routing-engine-orbit" aria-hidden="true" />
        <span className="routing-node-icon routing-engine-icon"><Compass aria-hidden="true" /></span>
        <span className="routing-node-label">AI Compass</span>
        <span className="routing-node-detail"><Sparkles aria-hidden="true" /> Evaluating candidates</span>
      </div>

      <div className="routing-flow-node routing-model-node">
        <span className="routing-node-icon"><Bot aria-hidden="true" /></span>
        <span className="routing-node-label">Recommended model</span>
        <span className="routing-node-detail">Best fit for the task</span>
      </div>
      <figcaption className="routing-visualization-caption">An illustrative view of the routing process</figcaption>
    </figure>
  );
}
