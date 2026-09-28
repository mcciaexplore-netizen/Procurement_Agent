"use client";

import { Fragment, useEffect, useState } from "react";
import type { Comparison, ComparedOffer } from "../page";

type Row = { category: string; label: string; badgeKind?: string; value: (offer: ComparedOffer) => string };

const ROWS: Row[] = [
  { category: "Pricing & Order", label: "Price", badgeKind: "best_price", value: (offer) => offer.price_status === "public" ? `${offer.currency ?? ""} ${offer.price} / ${offer.unit ?? "unit"}`.trim() : "Request quote" },
  { category: "Pricing & Order", label: "Eligible at requested quantity", value: (offer) => offer.quantity_eligible ? "Yes" : "No" },
  { category: "Availability & Logistics", label: "MOQ", badgeKind: "lowest_moq", value: (offer) => offer.moq !== null ? String(offer.moq) : "Unknown" },
  { category: "Availability & Logistics", label: "Availability", value: (offer) => offer.availability ?? "Unknown" },
  { category: "Availability & Logistics", label: "Data freshness", badgeKind: "freshest", value: (offer) => offer.freshness },
  { category: "Supplier", label: "Seller", value: (offer) => offer.seller_name },
  { category: "Supplier", label: "Source", value: (offer) => offer.source_name },
];

type ComparisonMatrixModalProps = {
  comparison: Comparison;
  onClose: () => void;
  onRemove: (offerId: string) => void;
};

export function ComparisonMatrixModal({ comparison, onClose, onRemove }: ComparisonMatrixModalProps) {
  const [diffOnly, setDiffOnly] = useState(false);
  const { product, quantity, offers, warnings } = comparison;
  const categories = [...new Set(ROWS.map((row) => row.category))];

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  function hasBadge(offer: ComparedOffer, kind?: string) {
    return kind ? offer.badges.some((badge) => badge.kind === kind) : false;
  }
  function badgeLabel(offer: ComparedOffer, kind?: string) {
    return kind ? offer.badges.find((badge) => badge.kind === kind)?.label : undefined;
  }
  function isUniform(row: Row) {
    return offers.every((offer) => row.value(offer) === row.value(offers[0]));
  }

  return (
    <div className="comparison-modal-backdrop" onClick={onClose}>
      <div className="comparison-modal" role="dialog" aria-modal="true" aria-labelledby="comparison-modal-title" onClick={(event) => event.stopPropagation()}>
        <header className="comparison-modal__header">
          <div>
            <p className="eyebrow">COMPARISON</p>
            <h2 id="comparison-modal-title">{product.normalized_name}{product.mpn ? ` · ${product.mpn}` : ""}</h2>
            <p>Requested quantity: {quantity ?? "not specified"}</p>
          </div>
          <div className="comparison-modal__controls">
            <label className="toggle-field">
              <input type="checkbox" checked={diffOnly} onChange={(event) => setDiffOnly(event.target.checked)} />
              <span><strong>Highlight differences only</strong></span>
            </label>
            <button type="button" className="comparison-modal__close" onClick={onClose} aria-label="Close comparison">×</button>
          </div>
        </header>
        <div className="comparison-modal__scroll">
          <table className="comparison-matrix">
            <thead>
              <tr>
                <th className="comparison-matrix__label-col">Spec</th>
                {offers.map((offer) => (
                  <th key={offer.offer_id}>
                    <div className="comparison-matrix__offer-head">
                      <strong>{offer.seller_name}</strong>
                      <span>{offer.source_name}</span>
                      <button type="button" onClick={() => onRemove(offer.offer_id)} aria-label={`Remove ${offer.seller_name} from comparison`}>Remove</button>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {categories.map((category) => {
                const rows = ROWS.filter((row) => row.category === category && (!diffOnly || !isUniform(row)));
                if (rows.length === 0) return null;
                return (
                  <Fragment key={category}>
                    <tr className="comparison-matrix__category-row"><td colSpan={offers.length + 1}>{category}</td></tr>
                    {rows.map((row) => (
                      <tr key={row.label}>
                        <th scope="row" className="comparison-matrix__label-col">{row.label}</th>
                        {offers.map((offer) => (
                          <td key={offer.offer_id} className={hasBadge(offer, row.badgeKind) ? "is-best" : undefined}>
                            {row.value(offer)}
                            {hasBadge(offer, row.badgeKind) && <span className="comparison-matrix__pill">{badgeLabel(offer, row.badgeKind)}</span>}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
        {warnings.length > 0 && <div className="comparison-modal__warnings">{warnings.map((warning) => <p className="notice" key={warning}>{warning}</p>)}</div>}
      </div>
    </div>
  );
}
