import React from 'react';
import { ReferenceSwing } from '../lib/api';
import { getBinBadgeColor, formatMedianMultiple } from '../utils/binUtils';

interface LevelsAtPlayPanelProps {
  references: ReferenceSwing[];
  totalReferenceCount: number;
  selectedLegId: string | null;
  hoveredLegId: string | null;
  onHoverLeg: (legId: string | null) => void;
  onSelectLeg: (legId: string) => void;
  isLoading?: boolean;
}

/**
 * LevelsAtPlayPanel displays top N legs ranked by salience.
 *
 * Per #430: Simplified sidebar showing only ranked legs.
 * - Shows "LEVELS AT PLAY (N/total)" header
 * - Hover highlights leg on chart
 * - Click selects leg (shows fibs persistently)
 * - Bin displayed as "N×" (median multiple)
 */
export const LevelsAtPlayPanel: React.FC<LevelsAtPlayPanelProps> = ({
  references,
  totalReferenceCount,
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
    <div className="space-y-1">
      {/* Header with count */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-medium text-app-muted uppercase tracking-wider">
          Levels at Play
        </span>
        <span className="text-[10px] text-app-muted">
          ({references.length}/{totalReferenceCount})
        </span>
      </div>

      {/* Leg list */}
      <div className="space-y-0.5">
        {references.map((ref, idx) => (
          <LegItem
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

interface LegItemProps {
  reference: ReferenceSwing;
  rank: number;
  isSelected: boolean;
  isHovered: boolean;
  onHover: (legId: string | null) => void;
  onClick: (legId: string) => void;
}

const LegItem: React.FC<LegItemProps> = ({
  reference,
  rank,
  isSelected,
  isHovered,
  onHover,
  onClick,
}) => {
  const binStyle = getBinBadgeColor(reference.bin);
  const directionColor = reference.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear';
  const directionArrow = reference.direction === 'bull' ? '▲' : '▼';
  const medianLabel = formatMedianMultiple(reference.median_multiple);

  // Compute salience bar width (max 100%)
  const saliencePercent = Math.min(100, Math.round(reference.salience_score * 100));

  // Price display (pivot price is the key level)
  const price = reference.pivot_price.toFixed(2);

  return (
    <div
      className={`flex items-center gap-1.5 px-2 py-1.5 rounded cursor-pointer transition-colors ${
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
      <span className="text-[10px] text-app-muted w-4 text-right font-mono">
        {rank}.
      </span>

      {/* Bin badge (median multiple) */}
      <span className={`px-1.5 py-0.5 rounded text-[9px] font-semibold ${binStyle.bg} ${binStyle.text}`}>
        {medianLabel}
      </span>

      {/* Direction arrow */}
      <span className={`text-[10px] ${directionColor}`}>
        {directionArrow}
      </span>

      {/* Price */}
      <span className="text-[10px] font-mono text-app-text flex-1">
        {price}
      </span>

      {/* Salience bar */}
      <div className="w-12 h-1.5 bg-app-border rounded-full overflow-hidden" title={`${saliencePercent}% salience`}>
        <div
          className={`h-full rounded-full ${
            saliencePercent >= 75 ? 'bg-trading-blue' :
            saliencePercent >= 50 ? 'bg-trading-blue/70' :
            saliencePercent >= 25 ? 'bg-trading-blue/50' :
            'bg-trading-blue/30'
          }`}
          style={{ width: `${saliencePercent}%` }}
        />
      </div>
    </div>
  );
};
