/**
 * Ecosystem panel + lifecycle blocks for the Model Pool and Inspect pages.
 *
 * Everything shown is derived from the backend catalogue. A figure that the backend cannot back with a real event
 * (last refresh, recent discoveries, source health) is not rendered: an offline snapshot says so instead.
 */
import { useMemo, useState } from 'react';
import { ArrowUpRight, ChevronDown, GitBranch, History, RadioTower } from 'lucide-react';
import { StatusPill } from '../ui/ds';
import type { Tone } from '../ui/ds';
import { Notice } from '../ui/EmptyState';
import { useAsync } from '../../hooks/useAsync';
import { getCatalogEcosystem, getCatalogFamilies } from '../../services/catalog.service';
import { formatInteger, formatTimestamp, humanizeToken } from '../../utils/format';
import { UNAVAILABLE } from '../../types';
import type { CatalogBlock, CatalogDestination, CatalogFamily, CatalogSourceHealth, GenerationStatus, ModelInfo, VerificationLevel } from '../../types';

const GENERATION_LABEL: Record<GenerationStatus, { text: string; tone: Tone; hint: string }> = {
  retained: { text: 'Current generation', tone: 'success', hint: 'One of the two latest verified generations of this family.' },
  superseded: { text: 'Superseded', tone: 'neutral', hint: 'Newer verified generations replace this one. Kept for history only.' },
  unmanaged: { text: 'No generation marker', tone: 'info', hint: 'The name has no version marker, so it is never retired automatically.' },
  pending_review: { text: 'Generation under review', tone: 'warning', hint: 'Evidence about its generation is ambiguous. Nothing is removed while it is reviewed.' },
  unverified: { text: 'Awaiting verification', tone: 'warning', hint: 'Detected but not yet confirmed by an official or independent source.' },
};
const VERIFICATION_LABEL: Record<VerificationLevel, { text: string; tone: Tone }> = {
  officially_confirmed: { text: 'Officially confirmed', tone: 'success' },
  corroborated: { text: 'Independently corroborated', tone: 'info' },
  detected: { text: 'Detected, unconfirmed', tone: 'warning' },
};
const KIND_LABEL: Record<string, string> = { documentation: 'Official documentation', model_page: 'Model page', model_repository: 'Model weights', provider_catalog: 'Provider listing' };
const AUTHORITY_LABEL: Record<string, string> = {
  official_documentation: 'Official documentation', developer_repository: "Developer's repository", provider_reported: 'Provider-reported', aggregator_reported: 'Aggregator-reported', merged: 'Merged sources',
};
const SOURCE_LABEL: Record<string, string> = { openrouter: 'OpenRouter public catalogue', huggingface: 'Hugging Face developer repositories', curated_snapshot: 'Curated documentation snapshot', announcements: 'Official release announcements (signals only)' };
const EVENT_LABEL: Record<string, string> = { model_discovered: 'Discovered', model_superseded: 'Superseded', model_published: 'Published', announcement_detected: 'Announced · unverified' };

function sourceTone(s: CatalogSourceHealth): Tone {
  if (s.status === 'ok') return 'success';
  if (s.status === 'partial' || s.status === 'rate_limited' || s.status === 'timed_out') return 'warning';
  if (s.status === 'failed') return 'danger';
  return 'neutral';
}

export function GenerationPill({ catalog }: { catalog: CatalogBlock | null | undefined }) {
  if (!catalog) return null;
  const info = GENERATION_LABEL[catalog.generation_status];
  const label = catalog.generation_label && catalog.generation_status !== 'unmanaged' ? `${info.text} · gen ${catalog.generation_label}` : info.text;
  return <StatusPill tone={info.tone} title={info.hint}>{label}</StatusPill>;
}

export function VerificationPill({ catalog }: { catalog: CatalogBlock | null | undefined }) {
  if (!catalog) return null;
  const v = VERIFICATION_LABEL[catalog.verification_level];
  return <StatusPill tone={v.tone}>{v.text}</StatusPill>;
}

export function DestinationLinks({ destinations }: { destinations: CatalogDestination[] }) {
  if (destinations.length === 0) return <p className="text-muted">No verified destination is recorded for this model.</p>;
  return (
    <ul className="eco-links">
      {destinations.map((d) => (
        <li key={d.url}>
          <a href={d.url} target="_blank" rel="noreferrer noopener" className="eco-link">
            <span><strong>{d.label}</strong><small>{KIND_LABEL[d.kind] ?? humanizeToken(d.kind)} · {d.provider} · {new URL(d.url).hostname}</small></span>
            <ArrowUpRight aria-hidden="true" />
          </a>
        </li>
      ))}
    </ul>
  );
}

function priceText(v: number | null): string {
  if (v === null) return 'Not published';
  if (v === 0) return 'Free';
  return `$${v < 1 ? v.toFixed(3) : v.toFixed(2)}`;
}

/** Inspect: where this model is lifecycle-wise, who says so, and every way to access it with its own price. */
export function LifecycleBlock({ model }: { model: ModelInfo }) {
  const c = model.catalog;
  if (!c) return null;
  const info = GENERATION_LABEL[c.generation_status];
  const prov = Object.entries(c.field_provenance);
  return (
    <>
      <div className="eco-block">
        <p className="field-label">Generation and verification</p>
        <div className="eco-pills"><GenerationPill catalog={c} /><VerificationPill catalog={c} />{c.retired ? <StatusPill tone="neutral">Retired</StatusPill> : null}</div>
        <p className="eco-note">{c.generation_reason ?? info.hint}</p>
        {c.retired && c.superseded_at ? <p className="eco-note">Retired {formatTimestamp(c.superseded_at)}. It stays visible here so earlier routing decisions and evaluations remain readable.</p> : null}
        {c.variants.length > 0 ? <p className="eco-note">Variant: {c.variants.map(humanizeToken).join(', ')}</p> : null}
      </div>
      <div className="eco-block">
        <p className="field-label">Ways to access it</p>
        <div className="eco-table-wrap">
          <table className="eco-table">
            <thead><tr><th scope="col">Provider</th><th scope="col">Provider model id</th><th scope="col">Input / 1M</th><th scope="col">Output / 1M</th><th scope="col">Reported by</th></tr></thead>
            <tbody>
              {c.offerings.map((o) => (
                <tr key={`${o.provider}|${o.model_id}`}>
                  <th scope="row">{o.provider}{o.listed ? null : <small> · no longer listed</small>}{o.deprecated ? <small> · deprecated</small> : null}</th>
                  <td><code>{o.model_id}</code></td>
                  <td>{priceText(o.input_per_million)}</td><td>{priceText(o.output_per_million)}</td>
                  <td>{AUTHORITY_LABEL[o.authority] ?? humanizeToken(o.authority)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="eco-note">Prices belong to each provider&apos;s offering. “Not published” means the source did not report one, not that it is free.</p>
      </div>
      <div className="eco-block">
        <p className="field-label">Official destinations</p>
        <DestinationLinks destinations={c.destinations} />
      </div>
      <div className="eco-block">
        <p className="field-label">Where each fact comes from</p>
        <dl className="eco-prov">
          {prov.map(([field, p]) => (<div key={field}><dt>{humanizeToken(field)}</dt><dd>{AUTHORITY_LABEL[p.authority] ?? humanizeToken(p.authority)} <small>({SOURCE_LABEL[p.source] ?? p.source})</small></dd></div>))}
          <div><dt>First seen</dt><dd>{formatTimestamp(c.first_seen_at)}</dd></div>
          {c.released_at ? <div><dt>Release date</dt><dd>{formatTimestamp(c.released_at)} <small>({humanizeToken(c.released_at_kind)})</small></dd></div> : null}
        </dl>
        {c.conflicts.length > 0 ? (
          <Notice tone="warning" title="Sources disagree">
            {c.conflicts.map((x) => `${humanizeToken(x.field)}: using ${x.chosen}; others reported ${x.others.join(', ')}.`).join(' ')}
          </Notice>
        ) : null}
      </div>
    </>
  );
}

function FamilyRow({ family }: { family: CatalogFamily }) {
  return (
    <li className="eco-family">
      <div className="eco-family-head">
        <strong>{humanizeToken(family.family)}</strong><small>{humanizeToken(family.track)} · {family.developer ?? 'unknown developer'}</small>
        {family.review_reason ? <StatusPill tone="warning" title={family.review_reason}>Under review</StatusPill> : null}
      </div>
      <ul className="eco-gens">
        {family.generations.map((g) => (
          <li key={g.generation_key}>
            <StatusPill tone={GENERATION_LABEL[g.retention]?.tone ?? 'neutral'} title={g.reason ?? undefined}>Gen {g.label} · {GENERATION_LABEL[g.retention]?.text ?? humanizeToken(g.retention)}</StatusPill>
            <span>{g.models.map((m) => m.name).join(', ')}</span>
          </li>
        ))}
        {family.unmanaged_models.length > 0 ? <li><StatusPill tone="info">No generation marker</StatusPill><span>{family.unmanaged_models.map((m) => m.name).join(', ')}</span></li> : null}
      </ul>
    </li>
  );
}

export function EcosystemPanel() {
  const eco = useAsync((signal) => getCatalogEcosystem(signal), []);
  const [open, setOpen] = useState(false);
  const families = useAsync((signal) => getCatalogFamilies(signal), [], { enabled: open });
  const data = eco.data;
  const multi = useMemo(() => (families.data ?? []).filter((f) => f.generations.length > 1 || f.review_reason), [families.data]);

  if (eco.isInitialLoad) return <section className="eco" aria-busy="true" aria-label="Model ecosystem"><p className="eco-note">Loading ecosystem status…</p></section>;
  if (eco.error || !data) {
    return <section className="eco" aria-label="Model ecosystem"><Notice tone="neutral" title="Ecosystem status unavailable">The catalogue status could not be loaded. The model list below is unaffected.</Notice></section>;
  }
  const t = data.totals;
  return (
    <section className="eco" aria-labelledby="eco-title">
      <header className="eco-head">
        <div>
          <p className="registry-eyebrow">Catalogue status</p>
          <h2 id="eco-title">What the catalogue knows right now</h2>
        </div>
        <StatusPill tone={data.live ? 'success' : 'neutral'} icon={<RadioTower />}>{data.live ? 'Live discovery' : 'Offline snapshot'}</StatusPill>
      </header>
      <dl className="eco-stats">
        <div><dt>Active models</dt><dd>{formatInteger(t.published)}</dd></div>
        <div><dt>Developers</dt><dd>{formatInteger(t.developers)}</dd></div>
        <div><dt>Current generations kept</dt><dd>{formatInteger(t.retained_generations)}</dd></div>
        <div><dt>Retired</dt><dd>{formatInteger(t.retired)}</dd></div>
        <div><dt>Awaiting verification</dt><dd>{formatInteger(t.awaiting_verification)}</dd></div>
        <div><dt>Last successful refresh</dt><dd>{data.live ? formatTimestamp(data.last_success_at) : UNAVAILABLE}</dd></div>
      </dl>
      {data.note ? <Notice tone="info" title="Snapshot data">{data.note}</Notice> : null}
      {data.store_error ? <Notice tone="warning" title="Catalogue store unreachable">Showing the last good view ({data.store_error}). Nothing was removed.</Notice> : null}
      {t.lineages_needing_review > 0 ? <Notice tone="warning" title="Generations under review">{t.lineages_needing_review} model famil{t.lineages_needing_review === 1 ? 'y has' : 'ies have'} ambiguous generation evidence. Nothing in {t.lineages_needing_review === 1 ? 'it is' : 'them is'} retired until the evidence is clear.</Notice> : null}
      {data.live && data.sources.length > 0 ? (
        <div className="eco-sources" role="list" aria-label="Discovery sources">
          {data.sources.map((s) => (
            <div key={s.source_id} role="listitem" className="eco-source">
              <StatusPill tone={sourceTone(s)}>{s.status === 'never_run' ? 'Not run yet' : humanizeToken(s.status)}</StatusPill>
              <span><strong>{SOURCE_LABEL[s.source_id] ?? humanizeToken(s.source_id)}</strong><small>{s.last_success_at ? `Last success ${formatTimestamp(s.last_success_at)}` : 'No successful refresh yet'}{s.consecutive_failures > 0 ? ` · ${s.consecutive_failures} consecutive failure${s.consecutive_failures === 1 ? '' : 's'}` : ''}</small></span>
            </div>
          ))}
        </div>
      ) : null}
      {data.live && data.recent_events.length > 0 ? (
        <div className="eco-recent">
          <p className="field-label"><History aria-hidden="true" /> Recent catalogue changes</p>
          <ul>{data.recent_events.map((e, i) => (<li key={`${e.entity_key}-${e.event_type}-${i}`}><StatusPill tone={e.event_type === 'model_superseded' || e.event_type === 'announcement_detected' ? 'neutral' : 'primary'}>{EVENT_LABEL[e.event_type] ?? humanizeToken(e.event_type)}</StatusPill><span>{e.name ?? e.entity_key}{e.event_type === 'announcement_detected' && e.to_state ? <> — {e.to_state === 'published' ? 'in catalogue' : e.to_state === 'awaiting_verification' || e.to_state === 'already_listed' ? 'detected in catalogue' : 'not in catalogue yet'}</> : null}</span><small>{formatTimestamp(e.occurred_at)}</small></li>))}</ul>
        </div>
      ) : null}
      {data.live && (data.recent_announcements?.length ?? 0) > 0 ? (
        <div className="eco-recent">
          <p className="field-label"><History aria-hidden="true" /> Recent release announcements (unverified signals)</p>
          <ul>{data.recent_announcements!.map((e, i) => (
            <li key={`${e.entity_key}-${i}`}>
              <StatusPill tone="neutral">{e.to_state === 'published' ? 'In catalogue' : e.to_state === 'awaiting_verification' || e.to_state === 'already_listed' ? 'Detected in catalogue' : 'Not in catalogue yet'}</StatusPill>
              <span>{e.entity_key.startsWith('https://') ? <a href={e.entity_key} target="_blank" rel="noopener noreferrer">{e.name ?? e.entity_key}</a> : (e.name ?? e.entity_key)}</span>
              <small>{formatTimestamp(e.occurred_at)}</small>
            </li>))}
          </ul>
          <p className="eco-note">Announcements are discovery signals only. A model appears in the catalogue after verification from catalogue sources, not from a post.</p>
        </div>
      ) : null}
      <button type="button" className="eco-toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <GitBranch aria-hidden="true" /> Generations by model family <ChevronDown aria-hidden="true" data-open={open || undefined} />
      </button>
      {open ? (
        families.isInitialLoad ? <p className="eco-note">Loading families…</p>
          : families.error ? <p className="eco-note">Families could not be loaded.</p>
            : (
              <>
                <p className="eco-note">Per family, the two latest verified generations stay active; older generations are retired but remain readable. Families with a single generation are not listed.</p>
                {multi.length === 0 ? <p className="eco-note">No family currently has more than one generation.</p> : <ul className="eco-families">{multi.map((f) => <FamilyRow key={f.lineage_key} family={f} />)}</ul>}
              </>
            )
      ) : null}
    </section>
  );
}
