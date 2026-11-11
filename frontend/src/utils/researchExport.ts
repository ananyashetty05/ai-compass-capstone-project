/**
 * Export a compact, reproducible record of a routing run and its baseline
 * observations. Generated responses are intentionally excluded; the query
 * text is included so the record can be matched to a research dataset.
 */
import type { BaselineResult, RouteResponse } from '../types';

function downloadText(filename: string, content: string, mimeType: string): void {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function estimatedRouteCost(result: RouteResponse): number | null {
  const costs = result.request_usage
    .map((usage) => usage.estimated_cost)
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  return costs.length ? costs.reduce((sum, value) => sum + value, 0) : null;
}

function providerLatency(result: RouteResponse): number | null {
  const latencies = result.request_usage.map((usage) => usage.latency_ms);
  if (!latencies.length || latencies.some((value) => typeof value !== 'number' || !Number.isFinite(value))) {
    return null;
  }
  return (latencies as number[]).reduce((sum, value) => sum + value, 0);
}

function routeRecord(result: RouteResponse) {
  const finalScore =
    result.model_scores.find((score) => score.model_id === result.final_model_id) ??
    result.model_scores.find((score) => score.model_id === result.selected_model_id);

  return {
    strategy: 'AI Compass Routing Strategy',
    selected_model: result.selected_model_id,
    final_model: result.final_model_id,
    quality_score: result.response_evaluation.quality_score,
    relevance_score: result.response_evaluation.relevance_score,
    completeness_score: result.response_evaluation.completeness_score,
    response_risk_score: result.response_evaluation.risk_score,
    accepted: result.response_evaluation.accepted,
    evaluator: result.response_evaluation.evaluation_method,
    cost_estimate_usd: estimatedRouteCost(result),
    provider_latency_ms: providerLatency(result),
    total_latency_ms: result.performance_metrics.total_latency_ms ?? null,
    routing_latency_ms: result.performance_metrics.routing_latency_ms ?? null,
    reliability_value: finalScore?.reliability_score ?? null,
    reliability_definition: 'Registry model reliability score; not the baseline blended reliability proxy',
    preference_alignment_proxy: finalScore?.preference_alignment ?? null,
    escalated: result.escalation_info.escalated,
    escalation_attempts: result.escalation_info.attempts,
    usage: result.request_usage,
    candidate_models: result.candidate_models,
    filtered_models: result.filtered_models,
    applied_weights: result.routing_explanation.applied_weights ?? {},
    applied_constraints: result.routing_explanation.applied_constraints ?? {},
  };
}

function baselineRecord(row: BaselineResult) {
  return {
    strategy: row.strategy,
    selected_model: row.selected_model,
    final_model: row.selected_model,
    quality_score: row.quality,
    relevance_score: null,
    completeness_score: null,
    response_risk_score: null,
    accepted: null,
    evaluator: 'deterministic_response_evaluation (backend baseline evaluator)',
    cost_estimate_usd: row.actual_estimated_cost,
    provider_latency_ms: row.latency_ms,
    total_latency_ms: null,
    routing_latency_ms: null,
    reliability_value: row.reliability,
    reliability_definition: 'Blended proxy: 0.7 × registry prior + 0.3 × response acceptance signal',
    preference_alignment_proxy: row.preference_alignment,
    escalated: row.escalated,
    escalation_attempts: null,
    usage: row.usage ?? null,
    candidate_models: null,
    filtered_models: null,
    applied_weights: null,
    applied_constraints: null,
  };
}

function timestampSlug(): string {
  return new Date().toISOString().replace(/[:.]/g, '-');
}

export function exportResearchJson(result: RouteResponse, baselines: BaselineResult[]): void {
  const record = {
    schema_version: 'aicompass-research-record-v1',
    exported_at: new Date().toISOString(),
    project: 'AI Compass',
    run_scope: 'single query; one AI Compass routing run plus separately executed baseline calls',
    query: result.query,
    profile: result.profile,
    query_analysis: result.query_analysis,
    ai_compass_run: routeRecord(result),
    baseline_runs: baselines.map(baselineRecord),
    methodological_caveats: [
      'A single query and one run per strategy are not sufficient to establish statistical superiority.',
      'The baseline endpoint applies its own default candidate filtering and does not inherit the original route hard constraints; candidate-pool parity is not guaranteed.',
      'Quality scores come from a deterministic heuristic evaluator, not human-validated factuality or semantic quality.',
      'Cost fields are estimates reported by adapters or registry metadata; they may not equal final provider invoices.',
      'AI Compass latency includes routing and may include escalation; baseline latency is provider-response latency. Compare latency only after aligning measurement definitions.',
      'AI Compass reliability is a registry model prior; baseline reliability is a blended prior-plus-acceptance proxy. These values are not directly comparable.',
      'Preference alignment is a query-to-model fit proxy, not a validated semantic measure of personal preference.',
    ],
  };
  downloadText(`aicompass-research-${timestampSlug()}.json`, JSON.stringify(record, null, 2), 'application/json');
}

function csvCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  return `"${text.replace(/"/g, '""')}"`;
}

export function exportResearchCsv(result: RouteResponse, baselines: BaselineResult[]): void {
  const route = routeRecord(result);
  const rows = [
    {
      run_type: 'ai_compass',
      query: result.query,
      profile: result.profile,
      strategy: route.strategy,
      selected_model: route.selected_model,
      final_model: route.final_model,
      quality_score: route.quality_score,
      cost_estimate_usd: route.cost_estimate_usd,
      provider_latency_ms: route.provider_latency_ms,
      total_latency_ms: route.total_latency_ms,
      routing_latency_ms: route.routing_latency_ms,
      reliability_value: route.reliability_value,
      reliability_definition: route.reliability_definition,
      preference_alignment_proxy: route.preference_alignment_proxy,
      accepted: route.accepted,
      escalated: route.escalated,
      escalation_attempts: route.escalation_attempts,
      evaluator: route.evaluator,
    },
    ...baselines.map((row) => {
      const baseline = baselineRecord(row);
      return {
        run_type: 'baseline',
        query: result.query,
        profile: result.profile,
        strategy: baseline.strategy,
        selected_model: baseline.selected_model,
        final_model: baseline.final_model,
        quality_score: baseline.quality_score,
        cost_estimate_usd: baseline.cost_estimate_usd,
        provider_latency_ms: baseline.provider_latency_ms,
        total_latency_ms: baseline.total_latency_ms,
        routing_latency_ms: baseline.routing_latency_ms,
        reliability_value: baseline.reliability_value,
        reliability_definition: baseline.reliability_definition,
        preference_alignment_proxy: baseline.preference_alignment_proxy,
        accepted: baseline.accepted,
        escalated: baseline.escalated,
        escalation_attempts: baseline.escalation_attempts,
        evaluator: baseline.evaluator,
      };
    }),
  ];
  const headers = Object.keys(rows[0]);
  const csv = [headers.map(csvCell).join(','), ...rows.map((row) => headers.map((key) => csvCell(row[key as keyof typeof row])).join(','))].join('\r\n');
  downloadText(`aicompass-research-${timestampSlug()}.csv`, csv, 'text/csv');
}
