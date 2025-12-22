import React, { useState, useRef, useEffect } from 'react';
import { DagStateResponse, DagLeg, DagPendingOrigin } from '../lib/api';
import { LegEvent, HighlightedDagItem } from '../types';
import { GitBranch, Circle, Target, History, ChevronDown, Paperclip } from 'lucide-react';
import { FollowedLegsPanel } from './FollowedLegsPanel';
import { FollowedLeg } from '../hooks/useFollowLeg';

// Types for attachable items
export type AttachableItem =
  | { type: 'leg'; data: DagLeg }
  | { type: 'pending_origin'; data: DagPendingOrigin };

interface DAGStatePanelProps {
  dagState: DagStateResponse | null;
  recentLegEvents: LegEvent[];
  isLoading?: boolean;
  onHoverItem?: (item: HighlightedDagItem | null) => void;
  highlightedItem?: HighlightedDagItem | null;
  // Attachment support
  attachedItems?: AttachableItem[];
  onAttachItem?: (item: AttachableItem) => void;
  onDetachItem?: (item: AttachableItem) => void;
  // Focus support (from chart click)
  focusedLegId?: string | null;
  // Follow Leg support (#267)
  followedLegs?: FollowedLeg[];
  onUnfollowLeg?: (legId: string) => void;
  onFollowedLegClick?: (legId: string) => void;
}

// Format price for display
const formatPrice = (value: number, decimals: number = 2): string => {
  return value.toFixed(decimals);
};

// Get color class based on direction
const getDirectionColor = (direction: 'bull' | 'bear'): string => {
  return direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear';
};

// Get background color class based on direction
const getDirectionBg = (direction: 'bull' | 'bear'): string => {
  return direction === 'bull' ? 'bg-trading-bull/10' : 'bg-trading-bear/10';
};

// Get status badge style
const getStatusStyle = (status: string): string => {
  switch (status) {
    case 'active':
      return 'bg-trading-blue/20 text-trading-blue border-trading-blue/30';
    case 'stale':
      return 'bg-trading-orange/20 text-trading-orange border-trading-orange/30';
    case 'invalidated':
      return 'bg-trading-bear/20 text-trading-bear border-trading-bear/30';
    default:
      return 'bg-app-card text-app-muted border-app-border';
  }
};

// Leg item component
interface LegItemProps {
  leg: DagLeg;
  isHighlighted?: boolean;
  isFocused?: boolean;
  isAttached?: boolean;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
  onClick?: () => void;
  innerRef?: React.Ref<HTMLDivElement>;
}

const LegItem: React.FC<LegItemProps> = ({ leg, isHighlighted, isFocused, isAttached, onMouseEnter, onMouseLeave, onClick, innerRef }) => (
  <div
    ref={innerRef}
    className={`text-xs p-2 rounded border transition-all duration-150 cursor-pointer ${
      isAttached
        ? 'border-trading-purple ring-2 ring-trading-purple/50'
        : isFocused
        ? 'border-trading-blue ring-2 ring-trading-blue/70 bg-trading-blue/20 scale-[1.02]'
        : isHighlighted
        ? 'border-trading-blue ring-2 ring-trading-blue/50 scale-[1.02]'
        : 'border-app-border/50 hover:border-app-border'
    } ${!isFocused ? getDirectionBg(leg.direction) : ''}`}
    onMouseEnter={onMouseEnter}
    onMouseLeave={onMouseLeave}
    onClick={onClick}
  >
    <div className="flex items-center justify-between mb-1">
      <span className={`font-medium ${getDirectionColor(leg.direction)}`}>
        {leg.direction.toUpperCase()}
      </span>
      <div className="flex items-center gap-1">
        {isAttached && <Paperclip size={10} className="text-trading-purple" />}
        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${getStatusStyle(leg.status)}`}>
          {leg.status}
        </span>
      </div>
    </div>
    <div className="grid grid-cols-2 gap-1 text-app-muted">
      <div>
        <span className="text-[10px] uppercase">Pivot:</span>{' '}
        <span className="font-mono">{formatPrice(leg.pivot_price)}</span>
      </div>
      <div>
        <span className="text-[10px] uppercase">Origin:</span>{' '}
        <span className="font-mono">{formatPrice(leg.origin_price)}</span>
      </div>
      <div>
        <span className="text-[10px] uppercase">Retr:</span>{' '}
        <span className="font-mono">{(leg.retracement_pct * 100).toFixed(1)}%</span>
      </div>
      <div>
        <span className="text-[10px] uppercase">Bars:</span>{' '}
        <span className="font-mono">{leg.bar_count}</span>
      </div>
      <div>
        <span className="text-[10px] uppercase">Impls:</span>{' '}
        <span className="font-mono">
          {leg.impulsiveness !== null ? `${leg.impulsiveness.toFixed(0)}%` : 'N/A'}
        </span>
      </div>
      <div>
        <span className="text-[10px] uppercase">Spiky:</span>{' '}
        <span className="font-mono">
          {leg.spikiness !== null ? `${leg.spikiness.toFixed(0)}%` : 'N/A'}
        </span>
      </div>
    </div>
  </div>
);

// Event type badge
const EventTypeBadge: React.FC<{ type: LegEvent['type'] }> = ({ type }) => {
  let style = '';
  let label = '';

  switch (type) {
    case 'LEG_CREATED':
      style = 'bg-trading-blue/20 text-trading-blue';
      label = 'CREATED';
      break;
    case 'LEG_PRUNED':
      style = 'bg-trading-orange/20 text-trading-orange';
      label = 'PRUNED';
      break;
    case 'LEG_INVALIDATED':
      style = 'bg-trading-bear/20 text-trading-bear';
      label = 'INVALID';
      break;
  }

  return (
    <span className={`text-[9px] px-1 py-0.5 rounded ${style}`}>
      {label}
    </span>
  );
};

// Helper to check if an item is attached
const isItemAttached = (
  attachedItems: AttachableItem[] | undefined,
  type: AttachableItem['type'],
  identifier: string
): boolean => {
  if (!attachedItems) return false;
  return attachedItems.some(item => {
    if (item.type !== type) return false;
    if (type === 'leg') {
      return (item.data as DagLeg).leg_id === identifier;
    } else if (type === 'pending_origin') {
      return (item.data as DagPendingOrigin).direction === identifier;
    }
    return false;
  });
};

export const DAGStatePanel: React.FC<DAGStatePanelProps> = ({
  dagState,
  recentLegEvents,
  isLoading = false,
  onHoverItem,
  highlightedItem,
  attachedItems,
  onAttachItem,
  onDetachItem,
  focusedLegId,
  followedLegs = [],
  onUnfollowLeg,
  onFollowedLegClick,
}) => {
  // Expansion state for each section
  const [bullLegsLimit, setBullLegsLimit] = useState(6);
  const [bearLegsLimit, setBearLegsLimit] = useState(6);

  // Refs for leg items to enable scroll-into-view
  const legRefsMap = useRef<Map<string, HTMLDivElement>>(new Map());

  // Scroll to focused leg when focusedLegId changes
  useEffect(() => {
    if (!focusedLegId || !dagState) return;

    // Find the leg to check direction and expand appropriate list
    const leg = dagState.active_legs.find(l => l.leg_id === focusedLegId);
    if (!leg) return;

    const directionLegs = dagState.active_legs.filter(l => l.direction === leg.direction);
    const legIndex = directionLegs.findIndex(l => l.leg_id === focusedLegId);

    // Expand the list if the focused leg is hidden
    if (leg.direction === 'bull' && legIndex >= bullLegsLimit) {
      setBullLegsLimit(legIndex + 1);
    } else if (leg.direction === 'bear' && legIndex >= bearLegsLimit) {
      setBearLegsLimit(legIndex + 1);
    }

    // Scroll to the leg element after a brief delay to allow render
    setTimeout(() => {
      const element = legRefsMap.current.get(focusedLegId);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }, 50);
  }, [focusedLegId, dagState, bullLegsLimit, bearLegsLimit]);

  // Toggle attachment for an item
  const handleItemClick = (item: AttachableItem, identifier: string) => {
    const attached = isItemAttached(attachedItems, item.type, identifier);
    if (attached) {
      onDetachItem?.(item);
    } else {
      onAttachItem?.(item);
    }
  };

  if (isLoading) {
    return (
      <div className="h-full bg-app-secondary border-t border-app-border flex items-center justify-center">
        <div className="text-app-muted text-sm">Loading market structure...</div>
      </div>
    );
  }

  if (!dagState) {
    return (
      <div className="h-full bg-app-secondary border-t border-app-border flex items-center justify-center">
        <div className="text-app-muted text-sm">No market structure available</div>
      </div>
    );
  }

  const { active_legs, pending_origins, leg_counts } = dagState;
  const bullLegs = active_legs.filter(leg => leg.direction === 'bull');
  const bearLegs = active_legs.filter(leg => leg.direction === 'bear');

  return (
    <div className="h-full bg-app-secondary border-t border-app-border flex flex-col font-sans text-sm">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-app-border bg-app-bg/40">
        <div className="flex items-center gap-2 text-app-text font-semibold tracking-wider uppercase">
          <GitBranch size={16} className="text-trading-purple" />
          <span>Current Structure</span>
        </div>
        <div className="h-4 w-px bg-app-border mx-2"></div>
        <div className="flex gap-3 text-xs">
          <span className="text-trading-bull">
            Bull: <span className="font-mono">{leg_counts.bull}</span>
          </span>
          <span className="text-trading-bear">
            Bear: <span className="font-mono">{leg_counts.bear}</span>
          </span>
        </div>
      </div>

      {/* Content Grid */}
      <div className="flex-1 grid grid-cols-4 divide-x divide-app-border/50 overflow-hidden">
        {/* Column 1: Bull Legs */}
        <div className="p-3 flex flex-col overflow-hidden">
          <div className="flex items-center gap-2 mb-2">
            <Circle size={12} className="text-trading-bull" />
            <span className="text-xs text-trading-bull font-medium uppercase tracking-wider">
              Bull Legs
            </span>
          </div>
          <div className="flex-1 overflow-y-auto space-y-2 pr-1">
            {bullLegs.length === 0 ? (
              <div className="text-xs text-app-muted italic">No bull legs</div>
            ) : (
              bullLegs.slice(0, bullLegsLimit).map((leg) => (
                <LegItem
                  key={leg.leg_id}
                  leg={leg}
                  isHighlighted={highlightedItem?.type === 'leg' && highlightedItem.id === leg.leg_id}
                  isFocused={focusedLegId === leg.leg_id}
                  isAttached={isItemAttached(attachedItems, 'leg', leg.leg_id)}
                  onMouseEnter={() => onHoverItem?.({ type: 'leg', id: leg.leg_id, direction: leg.direction })}
                  onMouseLeave={() => onHoverItem?.(null)}
                  onClick={() => handleItemClick({ type: 'leg', data: leg }, leg.leg_id)}
                  innerRef={(el) => {
                    if (el) {
                      legRefsMap.current.set(leg.leg_id, el);
                    } else {
                      legRefsMap.current.delete(leg.leg_id);
                    }
                  }}
                />
              ))
            )}
            {bullLegs.length > bullLegsLimit && (
              <button
                onClick={() => setBullLegsLimit(prev => prev + 10)}
                className="w-full text-xs text-trading-blue hover:text-trading-blue/80 text-center py-2 border border-dashed border-app-border rounded hover:border-trading-blue/50 transition-colors flex items-center justify-center gap-1"
              >
                <ChevronDown size={12} />
                +{bullLegs.length - bullLegsLimit} more
              </button>
            )}
          </div>
        </div>

        {/* Column 2: Bear Legs */}
        <div className="p-3 flex flex-col overflow-hidden">
          <div className="flex items-center gap-2 mb-2">
            <Circle size={12} className="text-trading-bear" />
            <span className="text-xs text-trading-bear font-medium uppercase tracking-wider">
              Bear Legs
            </span>
          </div>
          <div className="flex-1 overflow-y-auto space-y-2 pr-1">
            {bearLegs.length === 0 ? (
              <div className="text-xs text-app-muted italic">No bear legs</div>
            ) : (
              bearLegs.slice(0, bearLegsLimit).map((leg) => (
                <LegItem
                  key={leg.leg_id}
                  leg={leg}
                  isHighlighted={highlightedItem?.type === 'leg' && highlightedItem.id === leg.leg_id}
                  isFocused={focusedLegId === leg.leg_id}
                  isAttached={isItemAttached(attachedItems, 'leg', leg.leg_id)}
                  onMouseEnter={() => onHoverItem?.({ type: 'leg', id: leg.leg_id, direction: leg.direction })}
                  onMouseLeave={() => onHoverItem?.(null)}
                  onClick={() => handleItemClick({ type: 'leg', data: leg }, leg.leg_id)}
                  innerRef={(el) => {
                    if (el) {
                      legRefsMap.current.set(leg.leg_id, el);
                    } else {
                      legRefsMap.current.delete(leg.leg_id);
                    }
                  }}
                />
              ))
            )}
            {bearLegs.length > bearLegsLimit && (
              <button
                onClick={() => setBearLegsLimit(prev => prev + 10)}
                className="w-full text-xs text-trading-blue hover:text-trading-blue/80 text-center py-2 border border-dashed border-app-border rounded hover:border-trading-blue/50 transition-colors flex items-center justify-center gap-1"
              >
                <ChevronDown size={12} />
                +{bearLegs.length - bearLegsLimit} more
              </button>
            )}
          </div>
        </div>

        {/* Column 3: Followed Legs (#267) */}
        <FollowedLegsPanel
          followedLegs={followedLegs}
          onUnfollow={onUnfollowLeg || (() => {})}
          onLegClick={onFollowedLegClick}
        />

        {/* Column 4: Recent Events Log */}
        <div className="p-3 flex flex-col overflow-hidden">
          <div className="flex items-center gap-2 mb-2">
            <History size={12} className="text-app-muted" />
            <span className="text-xs text-app-muted font-medium uppercase tracking-wider">
              Recent Events
            </span>
          </div>
          <div className="flex-1 overflow-y-auto space-y-1 pr-1">
            {recentLegEvents.length === 0 ? (
              <div className="text-xs text-app-muted italic">No recent events</div>
            ) : (
              recentLegEvents.slice(0, 10).map((event, idx) => (
                <div
                  key={`${event.leg_id}-${idx}`}
                  className="text-xs p-1.5 rounded bg-app-card/30 border border-app-border/30"
                >
                  <div className="flex items-center gap-2 mb-0.5">
                    <EventTypeBadge type={event.type} />
                    <span className={`text-[10px] ${getDirectionColor(event.direction)}`}>
                      {event.direction.toUpperCase()}
                    </span>
                    <span className="text-[10px] text-app-muted ml-auto">@{event.bar_index}</span>
                  </div>
                  {event.reason && (
                    <div className="text-[10px] text-app-muted truncate" title={event.reason}>
                      {event.reason}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
