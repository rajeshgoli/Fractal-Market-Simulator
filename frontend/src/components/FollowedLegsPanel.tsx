/**
 * FollowedLegsPanel - Issue #267
 *
 * Displays followed legs with their state, last event, and unfollow action.
 * Replaces the Pending Origins column in DAGStatePanel.
 */

import React from 'react';
import { Eye, X } from 'lucide-react';
import { FollowedLeg, MAX_FOLLOWED_LEGS } from '../hooks/useFollowLeg';

interface FollowedLegsPanelProps {
  followedLegs: FollowedLeg[];
  onUnfollow: (legId: string) => void;
  onLegClick?: (legId: string) => void;
}

// Format price for display
const formatPrice = (value: number, decimals: number = 2): string => {
  return value.toFixed(decimals);
};

// Get state badge style (#408: 'forming'/'formed' → 'active')
const getStateBadgeStyle = (state: FollowedLeg['state']): string => {
  switch (state) {
    case 'active':
      return 'bg-trading-bull/20 text-trading-bull border-trading-bull/30';
    case 'pruned':
      return 'bg-trading-orange/20 text-trading-orange border-trading-orange/30';
    case 'invalidated':
      return 'bg-trading-bear/20 text-trading-bear border-trading-bear/30';
    default:
      return 'bg-app-card text-app-muted border-app-border';
  }
};

// Get event display name (#408: 'formed' → 'created')
const getEventDisplayName = (eventType: string | undefined): string => {
  if (!eventType) return '—';
  switch (eventType) {
    case 'created': return 'Created';
    case 'origin_breached': return 'Origin breached';
    case 'pivot_breached': return 'Pivot breached';
    case 'engulfed': return 'Engulfed';
    case 'pruned': return 'Pruned';
    case 'invalidated': return 'Invalidated';
    default: return eventType;
  }
};

export const FollowedLegsPanel: React.FC<FollowedLegsPanelProps> = ({
  followedLegs,
  onUnfollow,
  onLegClick,
}) => {
  return (
    <div className="p-3 flex flex-col overflow-hidden h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Eye size={12} className="text-green-400" />
          <span className="text-xs text-app-muted font-medium uppercase tracking-wider">
            Followed Legs
          </span>
        </div>
        <span className="text-xs text-app-muted">
          ({followedLegs.length}/{MAX_FOLLOWED_LEGS})
        </span>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {followedLegs.length === 0 ? (
          <div className="text-xs text-app-muted italic text-center py-4">
            Hover a leg and click the eye icon to follow
          </div>
        ) : (
          followedLegs.map((leg) => (
            <div
              key={leg.leg_id}
              className="text-xs p-2 rounded border border-app-border/50 hover:border-app-border transition-all cursor-pointer"
              style={{ backgroundColor: `${leg.color}15` }}
              onClick={() => onLegClick?.(leg.leg_id)}
            >
              {/* Row 1: Color swatch, direction, ID */}
              <div className="flex items-center gap-2 mb-1">
                {/* Color swatch */}
                <div
                  className="w-4 h-4 rounded-full flex-shrink-0"
                  style={{ backgroundColor: leg.color }}
                />
                {/* Direction */}
                <span className={leg.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}>
                  {leg.direction === 'bull' ? '▲' : '▼'}
                </span>
                {/* Leg ID (truncated) */}
                <span className="font-mono text-[10px] text-app-muted truncate flex-1" title={leg.leg_id}>
                  {leg.leg_id.length > 20 ? `${leg.leg_id.slice(0, 10)}...${leg.leg_id.slice(-8)}` : leg.leg_id}
                </span>
                {/* Unfollow button */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onUnfollow(leg.leg_id);
                  }}
                  className="p-1 hover:bg-red-900/30 rounded transition-colors group"
                  title="Unfollow leg"
                >
                  <X size={12} className="text-app-muted group-hover:text-red-400" />
                </button>
              </div>

              {/* Row 2: State and last event */}
              <div className="flex items-center justify-between">
                <span className={`text-[10px] px-1.5 py-0.5 rounded border ${getStateBadgeStyle(leg.state)}`}>
                  {leg.state}
                </span>
                <span className="text-[10px] text-app-muted">
                  {getEventDisplayName(leg.lastEvent)}
                </span>
              </div>

              {/* Row 3: Prices */}
              <div className="flex justify-between mt-1 text-[10px] text-app-muted">
                <span>P: <span className="font-mono">{formatPrice(leg.pivot_price)}</span></span>
                <span>O: <span className="font-mono">{formatPrice(leg.origin_price)}</span></span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
