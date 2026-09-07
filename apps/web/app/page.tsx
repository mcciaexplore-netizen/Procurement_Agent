"use client";

import { FormEvent, useEffect, useState } from "react";

type Offer = { id: string; seller_name: string; source_name: string; price_status: string; price: string | null; currency: string | null; unit: string | null; moq: number | null; availability: string | null; freshness: string; reasons: string[] };
type Group = { product: { id: string; manufacturer: string | null; mpn: string | null; normalized_name: string; category: string | null }; offers: Offer[] };
type ComparedOffer = { offer_id: string; seller_name: string; source_name: string; price_status: string; price: string | null; currency: string | null; unit: string | null; moq: number | null; availability: string | null; freshness: string; quantity_eligible: boolean; price_comparable: boolean; badges: { kind: string; label: string }[] };
type Comparison = { product: { normalized_name: string; mpn: string | null }; quantity: number | null; offers: ComparedOffer[]; warnings: string[] };
type Facet = { value: string; count: number };
type Facets = { categories: Facet[]; manufacturers: Facet[]; price_statuses: Facet[] };

const apiBase = () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function Home() {
  const [query, setQuery] = useState("STM32F407VGT6");
  const [quantity, setQuantity] = useState("500");
  const [groups, setGroups] = useState<Group[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [facets, setFacets] = useState<Facets>({ categories: [], manufacturers: [], price_statuses: [] });
  const [category, setCategory] = useState("");
  const [manufacturer, setManufacturer] = useState("");
  const [priceStatus, setPriceStatus] = useState("");
  const [freshOnly, setFreshOnly] = useState(false);
  const [smartQuery, setSmartQuery] = useState(true);
  const [message, setMessage] = useState("Search approved supplier offers. Coverage is intentionally limited.");

  useEffect(() => {
    fetch(`${apiBase()}/search/facets`).then(async (response) => {
      if (!response.ok) throw new Error("Could not load filters");
      setFacets(await response.json());
    }).catch(() => undefined);
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("Searching approved sources…");
    const params = new URLSearchParams({ q: query });
    if (quantity) params.set("quantity", quantity);
    if (category) params.set("category", category);
    if (manufacturer) params.set("manufacturer", manufacturer);
    if (priceStatus) params.set("price_status", priceStatus);
    if (freshOnly) params.set("fresh_only", "true");
    if (smartQuery) params.set("parse_natural_language", "true");
    try {
      const response = await fetch(`${apiBase()}/search?${params}`);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Search failed");
      setGroups(payload.groups);
      setSelectedIds([]);
      setComparison(null);
      setMessage(payload.groups.length ? "Prices, terms, and availability come from the source and may be incomplete." : "No current approved-source results. Try a part number or broader term.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not reach the catalog API.");
    }
  }

  function toggle(offerId: string) {
    setSelectedIds((current) => current.includes(offerId) ? current.filter((id) => id !== offerId) : current.length < 5 ? [...current, offerId] : current);
  }

  async function compare() {
    if (selectedIds.length < 2) return;
    const params = new URLSearchParams();
    selectedIds.forEach((id) => params.append("offer_id", id));
    if (quantity) params.set("quantity", quantity);
    try {
      const response = await fetch(`${apiBase()}/compare?${params}`);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Comparison failed");
      setComparison(payload);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not compare those offers.");
    }
  }

  return <main><header><p className="eyebrow">PERMISSION-FIRST PROCUREMENT SEARCH</p><h1>Find the right part. See the trade-offs.</h1><p>Compare current supplier offers, then continue with the original seller.</p></header>
    <form onSubmit={submit}><label>Part number or requirement<input value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Part number or requirement" /></label><label>Quantity<input type="number" min="1" value={quantity} onChange={(e) => setQuantity(e.target.value)} aria-label="Quantity" /></label><button type="submit">Search offers</button></form>
    <div className="filters" aria-label="Search filters"><label>Category<select value={category} onChange={(e) => setCategory(e.target.value)}><option value="">All categories</option>{facets.categories.map((facet) => <option key={facet.value} value={facet.value}>{facet.value} ({facet.count})</option>)}</select></label><label>Manufacturer<select value={manufacturer} onChange={(e) => setManufacturer(e.target.value)}><option value="">All manufacturers</option>{facets.manufacturers.map((facet) => <option key={facet.value} value={facet.value}>{facet.value} ({facet.count})</option>)}</select></label><label>Price status<select value={priceStatus} onChange={(e) => setPriceStatus(e.target.value)}><option value="">Any price status</option>{facets.price_statuses.map((facet) => <option key={facet.value} value={facet.value}>{facet.value.replace("_", " ")} ({facet.count})</option>)}</select></label><label className="fresh-filter"><input type="checkbox" checked={freshOnly} onChange={(e) => setFreshOnly(e.target.checked)} /> Fresh only</label><label className="fresh-filter"><input type="checkbox" checked={smartQuery} onChange={(e) => setSmartQuery(e.target.checked)} /> Parse quantity / INR budget</label></div>
    <p className="notice">{message}</p>
    {selectedIds.length > 0 && <aside className="compare-bar"><span>{selectedIds.length} selected</span><button onClick={compare} disabled={selectedIds.length < 2}>Compare selected</button><button className="secondary" onClick={() => { setSelectedIds([]); setComparison(null); }}>Clear</button></aside>}
    {comparison && <section className="comparison" aria-live="polite"><div><p className="eyebrow">COMPARISON</p><h2>{comparison.product.normalized_name}</h2><p>Requested quantity: {comparison.quantity ?? "not specified"}</p></div><div className="comparison-grid">{comparison.offers.map((offer) => <div className="comparison-card" key={offer.offer_id}><strong>{offer.seller_name}</strong><span>{offer.source_name} · {offer.freshness}</span><strong>{offer.price_status === "public" ? `${offer.currency ?? ""} ${offer.price} / ${offer.unit ?? "unit"}` : "Request quote"}</strong><span>MOQ {offer.moq ?? "unknown"} · {offer.availability ?? "unknown"}</span><div className="badges">{offer.badges.map((badge, index) => <span key={`${badge.kind}-${index}`}>{badge.label}</span>)}</div></div>)}</div><p className="notice">{comparison.warnings[0]}</p></section>}
    <section aria-live="polite">{groups.map((group) => <article key={group.product.id}><div><p className="eyebrow">{group.product.category ?? "Unclassified"}</p><h2>{group.product.normalized_name}</h2><p>{group.product.manufacturer ?? "Manufacturer unknown"}{group.product.mpn ? ` · ${group.product.mpn}` : ""}</p></div><div className="offers">{group.offers.map((offer) => <div className="offer" key={offer.id}><label className="select"><input type="checkbox" checked={selectedIds.includes(offer.id)} onChange={() => toggle(offer.id)} /> Compare</label><div><strong>{offer.seller_name}</strong><span>{offer.source_name} · {offer.freshness}</span></div><div><strong>{offer.price_status === "public" ? `${offer.currency ?? ""} ${offer.price} / ${offer.unit ?? "unit"}` : "Request quote"}</strong><span>MOQ {offer.moq ?? "unknown"} · {offer.availability ?? "availability unknown"}</span></div><form className="outbound" method="post" action={`${apiBase()}/outbound/${offer.id}`} target="_blank"><button type="submit">Visit seller</button></form><p>{offer.reasons.join(" · ")}</p></div>)}</div></article>)}</section>
  </main>;
}
