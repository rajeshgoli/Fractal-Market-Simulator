/**
 * EventInspectionPopup - Issue #267
 *
 * Popup displayed when clicking on a candle with event markers.
 * Shows event details and allows attaching events to feedback.
 */

import React from 'react';
import { X, Paperclip, ExternalLink } from 'lucide-react';
import { LifecycleEventWithLegInfo } from '../hooks/useFollowLeg';

interface EventInspectionPopupProps {
  events: LifecycleEventWithLegInfo[];
  barIndex: number;
  csvIndex?: number;
  position: { x: number; y: number };
  onClose: () => void;
  onAttachEvent: (event: LifecycleEventWithLegInfo) => void;
  onFocusLeg?: (legId: string) => void;
}

/**
 * Get event type badge style
 */
function getEventBadgeStyle(eventType: string): string {
  switch (eventType) {
    case 'formed':
      return 'bg-trading-bull/20 text-trading-bull border-trading-bull/30';
    case 'invalidated':
      return 'bg-trading-bear/20 text-trading-bear border-trading-bear/30';
    case 'engulfed':
      return 'bg-trading-bear/20 text-trading-bear border-trading-bear/30';
    case 'pruned':
      return 'bg-trading-orange/20 text-trading-orange border-trading-orange/30';
    case 'origin_breached':
    case 'pivot_breached':
      return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
    default:
      return 'bg-app-card text-app-muted border-app-border';
  }
}

/**
 * Get event type display name
 */
function getEventDisplayName(eventType: string): string {
  switch (eventType) {
    case 'formed':
      return 'Formed';
    case 'invalidated':
      return 'Invalidated';
    case 'engulfed':
      return 'Engulfed';
    case 'pruned':
      return 'Pruned';
    case 'origin_breached':
      return 'Origin Breached';
    case 'pivot_breached':
      return 'Pivot Breached';
    default:
      return eventType;
  }
}

export const EventInspectionPopup: React.FC<EventInspectionPopupProps> = ({
  events,
  barIndex,
  csvIndex,
  position,
  onClose,
  onAttachEvent,
  onFocusLeg,
}) => {
  return (
    <div
      className="fixed bg-app-secondary border border-app-border rounded-lg shadow-lg z-50 min-w-[280px] max-w-[360px]"
      style={{
        left: position.x,
        top: position.y,
        transform: 'translate(-50%, -100%) translateY(-10px)', // Center above click point
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-app-border bg-app-bg/50 rounded-t-lg">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-app-text">Events</span>
          <span className="text-xs text-app-muted">
            @{barIndex}
            {csvIndex !== undefined && ` (CSV: ${csvIndex})`}
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1 hover:bg-app-card rounded transition-colors"
        >
          <X size={14} className="text-app-muted" />
        </button>
      </div>

      {/* Events list */}
      <div className="p-2 space-y-2 max-h-[300px] overflow-y-auto">
        {events.map((event, idx) => (
          <div
            key={`${event.leg_id}-${event.event_type}-${idx}`}
            className="p-2 rounded border border-app-border/50 bg-app-card/30 hover:border-app-border transition-colors"
          >
            {/* Event header */}
            <div className="flex items-center gap-2 mb-1">
              {/* Color swatch */}
              <div
                className="w-3 h-3 rounded-full flex-shrink-0"
                style={{ backgroundColor: event.legColor }}
              />
              {/* Direction indicator */}
              <span className={event.legDirection === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}>
                {event.legDirection === 'bull' ? '▲' : '▼'}
              </span>
              {/* Event type badge */}
              <span className={`text-[10px] px-1.5 py-0.5 rounded border ${getEventBadgeStyle(event.event_type)}`}>
                {getEventDisplayName(event.event_type)}
              </span>
              {/* Timestamp */}
              <span className="text-[10px] text-app-muted ml-auto">
                {new Date(event.timestamp).toLocaleTimeString()}
              </span>
            </div>

            {/* Explanation */}
            <div className="text-xs text-app-muted mb-2">
              {event.explanation}
            </div>

            {/* Action buttons */}
            <div className="flex items-center gap-2">
              {/* Attach to feedback */}
              <button
                onClick={() => onAttachEvent(event)}
                className="flex items-center gap-1 text-[10px] px-2 py-1 bg-trading-purple/20 text-trading-purple rounded hover:bg-trading-purple/30 transition-colors"
                title="Attach to feedback"
              >
                <Paperclip size={10} />
                Attach
              </button>
              {/* Focus leg */}
              {onFocusLeg && (
                <button
                  onClick={() => onFocusLeg(event.leg_id)}
                  className="flex items-center gap-1 text-[10px] px-2 py-1 bg-trading-blue/20 text-trading-blue rounded hover:bg-trading-blue/30 transition-colors"
                  title="Focus leg on chart"
                >
                  <ExternalLink size={10} />
                  Focus
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
