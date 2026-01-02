import React from 'react';
import { ReferenceStateResponseExtended, LevelCrossEvent, LifecycleEvent, ReferenceSwing } from '../lib/api';
import { Zap, AlertCircle, X, Layers } from 'lucide-react';
import { LevelsAtPlayBottomPanel } from './LevelsAtPlayBottomPanel';

interface ReferenceTelemetryPanelProps {
  referenceState: ReferenceStateResponseExtended | null;
  crossingEvents: LevelCrossEvent[];
  lifecycleEvents?: LifecycleEvent[];  // Recent lifecycle events for references
  trackError: string | null;
  onClearTrackError: () => void;
  onEventHover?: (legId: string | null) => void;  // Hover callback to highlight leg on chart
  // Levels at Play (Issue #445)
  allReferences?: ReferenceSwing[];  // All references (not paginated)
  selectedLegId?: string | null;
  hoveredLegId?: string | null;
  onHoverLeg?: (legId: string | null) => void;
  onSelectLeg?: (legId: string) => void;
}

// Event type labels for display
const EVENT_TYPE_LABELS: Record<string, { label: string; color: string; icon: 'formed' | 'invalidated' | 'completed' }> = {
  created: { label: 'Formed', color: 'text-trading-bull', icon: 'formed' },
  origin_breached: { label: 'Origin breach', color: 'text-orange-400', icon: 'invalidated' },
  pivot_breached: { label: 'Pivot breach', color: 'text-red-400', icon: 'invalidated' },
  engulfed: { label: 'Engulfed', color: 'text-red-400', icon: 'invalidated' },
  pruned: { label: 'Pruned', color: 'text-yellow-400', icon: 'invalidated' },
  invalidated: { label: 'Invalidated', color: 'text-red-400', icon: 'invalidated' },
};

export const ReferenceTelemetryPanel: React.FC<ReferenceTelemetryPanelProps> = ({
  referenceState,
  crossingEvents,
  lifecycleEvents = [],
  trackError,
  onClearTrackError,
  onEventHover,
  // Levels at Play (Issue #445)
  allReferences = [],
  selectedLegId = null,
  hoveredLegId = null,
  onHoverLeg = () => {},
  onSelectLeg = () => {},
}) => {
  if (!referenceState) {
    return (
      <div className="h-full bg-app-secondary p-4 overflow-y-auto border-t border-app-border">
        <div className="text-app-muted text-sm text-center py-8">
          Loading reference state...
        </div>
      </div>
    );
  }

  // Warming up state
  if (referenceState.is_warming_up) {
    const [current, required] = referenceState.warmup_progress;
    const progress = (current / required) * 100;

    return (
      <div className="h-full bg-app-secondary p-4 overflow-y-auto border-t border-app-border">
        <div className="text-center py-8">
          <div className="text-app-muted text-sm mb-3">Warming up...</div>
          <div className="w-full bg-app-card rounded-full h-2 mb-2">
            <div
              className="bg-trading-blue h-2 rounded-full transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="text-xs text-app-muted">
            {current} / {required} swings collected
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full bg-app-secondary p-3 overflow-hidden border-t border-app-border">
      {/* Track error notification */}
      {trackError && (
        <div className="mb-2 px-3 py-2 bg-red-500/20 border border-red-500/40 rounded-lg flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle size={14} className="text-red-400" />
            <span className="text-xs text-red-400">{trackError}</span>
          </div>
          <button
            onClick={onClearTrackError}
            className="p-1 hover:bg-red-500/20 rounded"
          >
            <X size={12} className="text-red-400" />
          </button>
        </div>
      )}

      {/* Two-column layout: LEVELS AT PLAY (wide) + EVENTS (narrow) - Issue #445 */}
      <div className="flex gap-3 h-full">
        {/* LEVELS AT PLAY - Multi-column, all legs */}
        <div className="flex-1 bg-app-card rounded-lg border border-app-border flex flex-col min-w-0">
          <div className="flex items-center gap-2 p-2 border-b border-app-border shrink-0">
            <Layers size={14} className="text-trading-blue" />
            <h3 className="text-xs font-semibold text-app-text uppercase tracking-wider">
              Levels at Play
            </h3>
            <span className="text-[10px] text-app-muted">
              ({allReferences.length})
            </span>
          </div>
          <div className="flex-1 overflow-hidden">
            <LevelsAtPlayBottomPanel
              references={allReferences}
              selectedLegId={selectedLegId}
              hoveredLegId={hoveredLegId}
              onHoverLeg={onHoverLeg}
              onSelectLeg={onSelectLeg}
            />
          </div>
        </div>

        {/* EVENTS - Lifecycle events */}
        <div className="w-64 shrink-0 bg-app-card rounded-lg border border-app-border flex flex-col">
          <div className="flex items-center gap-2 p-2 border-b border-app-border shrink-0">
            <Zap size={14} className="text-yellow-400" />
            <h3 className="text-xs font-semibold text-app-text uppercase tracking-wider">Events</h3>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {(() => {
              // Combine lifecycle and crossing events, prioritizing lifecycle
              const allEvents: Array<{ type: 'lifecycle' | 'crossing'; event: LifecycleEvent | LevelCrossEvent }> = [
                ...lifecycleEvents.map(e => ({ type: 'lifecycle' as const, event: e })),
                ...crossingEvents.map(e => ({ type: 'crossing' as const, event: e })),
              ];
              // Take last 20 events, reversed for most recent first
              const recentEvents = allEvents.slice(-20).reverse();

              if (recentEvents.length === 0) {
                return (
                  <div className="text-xs text-app-muted text-center py-4">
                    No events yet
                  </div>
                );
              }

              return (
                <div className="space-y-0.5">
                  {recentEvents.map((item, idx) => {
                    if (item.type === 'lifecycle') {
                      const event = item.event as LifecycleEvent;
                      const eventInfo = EVENT_TYPE_LABELS[event.event_type] || { label: event.event_type, color: 'text-app-muted', icon: 'invalidated' };
                      return (
                        <div
                          key={`lifecycle-${event.leg_id}-${event.bar_index}-${idx}`}
                          className="text-[10px] flex items-center gap-1.5 py-1 px-1.5 cursor-pointer hover:bg-app-border/30 rounded transition-colors"
                          onMouseEnter={() => onEventHover?.(event.leg_id)}
                          onMouseLeave={() => onEventHover?.(null)}
                        >
                          <span className={event.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}>
                            {event.direction === 'bull' ? '\u25B2' : '\u25BC'}
                          </span>
                          <span className={`${eventInfo.color} flex-1`}>
                            {eventInfo.label}
                          </span>
                        </div>
                      );
                    } else {
                      const event = item.event as LevelCrossEvent;
                      return (
                        <div
                          key={`crossing-${event.leg_id}-${event.bar_index}-${idx}`}
                          className="text-[10px] flex items-center gap-1.5 py-1 px-1.5 cursor-pointer hover:bg-app-border/30 rounded transition-colors"
                          onMouseEnter={() => onEventHover?.(event.leg_id)}
                          onMouseLeave={() => onEventHover?.(null)}
                        >
                          <span className={event.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}>
                            {event.direction === 'bull' ? '\u25B2' : '\u25BC'}
                          </span>
                          <span className="text-app-muted flex-1">
                            Crossed {(event.level_crossed ?? 0).toFixed(2)}
                          </span>
                          <span className={event.cross_direction === 'up' ? 'text-trading-bull' : 'text-trading-bear'}>
                            {event.cross_direction === 'up' ? '\u2191' : '\u2193'}
                          </span>
                        </div>
                      );
                    }
                  })}
                </div>
              );
            })()}
          </div>
        </div>
      </div>
    </div>
  );
};
