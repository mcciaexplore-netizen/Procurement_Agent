"use client";

import { FormEvent, useState } from "react";

type Source = { id: string; name: string; status: string; policy: { version: string; approved: boolean; allowed_scopes: string[]; evidence_url: string } | null };
type SourceHealth = { source_id: string; source_name: string; status: string; offer_count: number; capture_count: number; freshness: { fresh: number; aging: number; stale: number; source_unavailable: number }; public_price_completeness: number | null; commercial_field_completeness: number | null; redirect_failures: number };

const apiBase = () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function SourceAdmin() {
  const [token, setToken] = useState("");
  const [actor, setActor] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [health, setHealth] = useState<SourceHealth[]>([]);
  const [message, setMessage] = useState("Enter an administrator token to view or onboard sources.");
  const [form, setForm] = useState({ id: "", name: "", base_url: "https://", owner: "", version: "v1", allowed_scope: "https://", allowed_domain: "", rate_budget: "10", freshness_sla: "24", evidence_url: "https://" });

  const headers = () => ({ "Content-Type": "application/json", "X-Admin-Token": token, "X-Actor": actor || "admin" });
  const update = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }));

  async function refresh() {
    const [sourcesResponse, healthResponse] = await Promise.all([
      fetch(`${apiBase()}/admin/sources`, { headers: headers() }),
      fetch(`${apiBase()}/admin/source-health`, { headers: headers() }),
    ]);
    const [sourcesPayload, healthPayload] = await Promise.all([sourcesResponse.json(), healthResponse.json()]);
    if (!sourcesResponse.ok) throw new Error(sourcesPayload.detail ?? "Could not load sources");
    if (!healthResponse.ok) throw new Error(healthPayload.detail ?? "Could not load source health");
    setSources(sourcesPayload);
    setHealth(healthPayload);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const response = await fetch(`${apiBase()}/admin/sources`, { method: "POST", headers: headers(), body: JSON.stringify({ id: form.id, name: form.name, base_url: form.base_url, owner: form.owner, policy: { version: form.version, allowed_scopes: [form.allowed_scope], allowed_domains: [form.allowed_domain], rate_budget_per_minute: Number(form.rate_budget), freshness_sla_hours: Number(form.freshness_sla), evidence_url: form.evidence_url } }) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Source registration failed");
      setMessage(`Policy ${payload.policy.version} submitted for ${payload.name}. Approve it explicitly before importing.`);
      await refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Source registration failed"); }
  }

  async function approve(source: Source) {
    if (!source.policy) return;
    try {
      const response = await fetch(`${apiBase()}/admin/sources/${source.id}/policies/${source.policy.version}/approve`, { method: "POST", headers: headers() });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Approval failed");
      setMessage(`${payload.name} is active. Only the approved scope may now be imported.`);
      await refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Approval failed"); }
  }

  return <main><header><p className="eyebrow">SOURCE OPERATIONS</p><h1>Approve before you acquire.</h1><p>Register a supplier source with auditable rights evidence and a bounded operating policy.</p></header>
    <section className="admin-panel"><div className="admin-access"><label>Admin token<input type="password" value={token} onChange={(e) => setToken(e.target.value)} /></label><label>Actor<input value={actor} onChange={(e) => setActor(e.target.value)} placeholder="your work identity" /></label><button onClick={() => refresh().catch((error) => setMessage(error.message))}>Load sources</button></div><p className="notice">{message}</p></section>
    <form className="admin-grid" onSubmit={submit}><h2>Register a draft source</h2><label>Source ID<input required value={form.id} onChange={(e) => update("id", e.target.value)} placeholder="supplier-feed-01" /></label><label>Display name<input required value={form.name} onChange={(e) => update("name", e.target.value)} /></label><label>Base HTTPS URL<input required value={form.base_url} onChange={(e) => update("base_url", e.target.value)} /></label><label>Owner<input required value={form.owner} onChange={(e) => update("owner", e.target.value)} placeholder="team@example.com" /></label><label>Policy version<input required value={form.version} onChange={(e) => update("version", e.target.value)} /></label><label>Allowed HTTPS scope<input required value={form.allowed_scope} onChange={(e) => update("allowed_scope", e.target.value)} /></label><label>Allowed hostname<input required value={form.allowed_domain} onChange={(e) => update("allowed_domain", e.target.value)} placeholder="supplier.example.in" /></label><label>Requests / minute<input required type="number" min="1" value={form.rate_budget} onChange={(e) => update("rate_budget", e.target.value)} /></label><label>Freshness SLA (hours)<input required type="number" min="1" value={form.freshness_sla} onChange={(e) => update("freshness_sla", e.target.value)} /></label><label>Evidence URL<input required value={form.evidence_url} onChange={(e) => update("evidence_url", e.target.value)} /></label><button type="submit">Submit policy for approval</button></form>
    <section className="source-list">{sources.map((source) => <article key={source.id}><p className="eyebrow">{source.status}</p><h2>{source.name}</h2><p>{source.id} · {source.policy?.version ?? "no policy"}</p>{source.policy && <p className="notice">Scope: {source.policy.allowed_scopes.join(", ")}</p>}{source.policy && !source.policy.approved && <button onClick={() => approve(source)}>Approve and activate</button>}</article>)}</section>
    {health.length > 0 && <section><p className="eyebrow">SOURCE HEALTH</p><div className="source-list">{health.map((source) => <article key={source.source_id}><p className="eyebrow">{source.status} · {source.offer_count} offers</p><h2>{source.source_name}</h2><p>Fresh {source.freshness.fresh} · Aging {source.freshness.aging} · Stale {source.freshness.stale}</p><p className="notice">Public-price completeness: {source.public_price_completeness === null ? "n/a" : `${Math.round(source.public_price_completeness * 100)}%`} · Commercial fields: {source.commercial_field_completeness === null ? "n/a" : `${Math.round(source.commercial_field_completeness * 100)}%`}</p><p className="notice">Captures: {source.capture_count} · Redirect failures: {source.redirect_failures}</p></article>)}</div></section>}
  </main>;
}
