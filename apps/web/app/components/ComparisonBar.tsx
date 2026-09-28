"use client";

export type ComparisonBarOffer = { id: string; seller_name: string };

type ComparisonBarProps = {
  offers: ComparisonBarOffer[];
  maxSlots: number;
  onRemove: (offerId: string) => void;
  onClear: () => void;
  onCompare: () => void;
};

export function ComparisonBar({ offers, maxSlots, onRemove, onClear, onCompare }: ComparisonBarProps) {
  if (offers.length === 0) return null;

  return (
    <aside className="comparison-bar" aria-label="Offer comparison tray">
      <div className="comparison-bar__chips">
        {offers.map((offer) => (
          <span className="comparison-bar__chip" key={offer.id}>
            <span className="comparison-bar__avatar" aria-hidden="true">{offer.seller_name.slice(0, 2).toUpperCase()}</span>
            <span className="comparison-bar__chip-label">{offer.seller_name}</span>
            <button type="button" onClick={() => onRemove(offer.id)} aria-label={`Remove ${offer.seller_name} from comparison`}>×</button>
          </span>
        ))}
      </div>
      <span className="comparison-bar__count">Comparing {offers.length} of {maxSlots}</span>
      <div className="comparison-bar__actions">
        <button type="button" className="secondary" onClick={onClear}>Clear all</button>
        <button type="button" onClick={onCompare} disabled={offers.length < 2}>Compare offers ({offers.length})</button>
      </div>
    </aside>
  );
}
