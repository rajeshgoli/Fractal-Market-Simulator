import React from 'react';
import { ReferenceSwing } from '../lib/api';
import { getBinBadgeColor, formatMedianMultiple } from '../utils/binUtils';

interface LevelsAtPlayBottomPanelProps {
  references: ReferenceSwing[];
  selectedLegId: string | null;
  hoveredLegId: string | null;
  onHoverLeg: (legId: string | null) => void;
  onSelectLeg: (legId: string) => void;
  isLoading?: boolean;
}

/**
 * LevelsAtPlayBottomPanel displays all legs in a multi-column layout.
 *
 * Per #445: Moved from sidebar to bottom panel, expanded to show all legs.
 * - Multi-column layout that fills available space
 * - Hover highlights leg on chart
 * - Click selects leg (shows fibs persistently)
 */
export const LevelsAtPlayBottomPanel: React.FC<LevelsAtPlayBottomPanelProps> = ({
  references,
  selectedLegId,
  hoveredLegId,
  onHoverLeg,
  onSelectLeg,
  isLoading = false,
}) => {
  if (isLoading) {
    return (
      <div className="text-xs text-app-muted text-center py-4">
        Loading...
      </div>
    );
  }

  if (references.length === 0) {
    return (
      <div className="text-xs text-app-muted text-center py-4">
        No active references
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      {/* Multi-column grid layout */}
      <div className="grid grid-cols-3 gap-x-4 gap-y-0.5 p-2">
        {references.map((ref, idx) => (
          <LegItemCompact
            key={ref.leg_id}
            reference={ref}
            rank={idx + 1}
            isSelected={selectedLegId === ref.leg_id}
            isHovered={hoveredLegId === ref.leg_id}
            onHover={onHoverLeg}
            onClick={onSelectLeg}
          />
        ))}
      </div>
    </div>
  );
};

interface LegItemCompactProps {
  reference: ReferenceSwing;
  rank: number;
  isSelected: boolean;
  isHovered: boolean;
  onHover: (legId: string | null) => void;
  onClick: (legId: string) => void;
}

const LegItemCompact: React.FC<LegItemCompactProps> = ({
  reference,
  rank,
  isSelected,
  isHovered,
  onHover,
  onClick,
}) => {
  const binStyle = getBinBadgeColor(reference.bin);
  const directionColor = reference.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear';
  const directionArrow = reference.direction === 'bull' ? '\u25B2' : '\u25BC';
  const medianLabel = formatMedianMultiple(reference.median_multiple);

  // Price display (pivot price is the key level)
  const price = reference.pivot_price.toFixed(2);

  return (
    <div
      className={`flex items-center gap-1 px-1.5 py-1 rounded cursor-pointer transition-colors ${
        isSelected
          ? 'bg-trading-blue/20 ring-1 ring-trading-blue'
          : isHovered
          ? 'bg-app-card/60'
          : 'hover:bg-app-card/40'
      }`}
      onMouseEnter={() => onHover(reference.leg_id)}
      onMouseLeave={() => onHover(null)}
      onClick={() => onClick(reference.leg_id)}
    >
      {/* Rank */}
      <span className="text-[9px] text-app-muted w-4 text-right font-mono shrink-0">
        {rank}.
      </span>

      {/* Bin badge (median multiple) */}
      <span className={`px-1 py-0.5 rounded text-[8px] font-semibold shrink-0 ${binStyle.bg} ${binStyle.text}`}>
        {medianLabel}
      </span>

      {/* Direction arrow */}
      <span className={`text-[9px] shrink-0 ${directionColor}`}>
        {directionArrow}
      </span>

      {/* Price */}
      <span className="text-[9px] font-mono text-app-text truncate">
        {price}
      </span>
    </div>
  );
};
