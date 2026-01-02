import React from 'react';
import { ReferenceStateResponseExtended, LevelCrossEvent, LifecycleEvent } from '../lib/api';
import { TrendingUp, Layers, Filter, Eye, EyeOff, Crosshair, AlertCircle, X, Zap } from 'lucide-react';
import { getBinBadgeColor, formatMedianMultiple } from '../utils/binUtils';

interface ReferenceTelemetryPanelProps {
  referenceState: ReferenceStateResponseExtended | null;
  showFiltered: boolean;
  onToggleShowFiltered: () => void;
  crossingEvents: LevelCrossEvent[];
  lifecycleEvents?: LifecycleEvent[];  // Recent lifecycle events for references
  trackError: string | null;
  onClearTrackError: () => void;
  trackedCount: number;
  onEventHover?: (legId: string | null) => void;  // Hover callback to highlight leg on chart
}

// Filter reason display names and colors
const FILTER_REASON_LABELS: Record<string, { label: string; color: string }> = {
  not_formed: { label: 'Not Formed', color: 'text-yellow-400' },
  pivot_breached: { label: 'Pivot Breached', color: 'text-red-400' },
  origin_breached: { label: 'Origin Breached', color: 'text-orange-400' },
  completed: { label: 'Completed', color: 'text-blue-400' },
  cold_start: { label: 'Cold Start', color: 'text-gray-400' },
};

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
  showFiltered,
  onToggleShowFiltered,
  crossingEvents,
  lifecycleEvents = [],
  trackError,
  onClearTrackError,
  trackedCount,
  onEventHover,
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

  const { by_bin, by_direction, references, filter_stats } = referenceState;

  // Find biggest, most salient, and most impulsive
  const biggestRef = references.length > 0
    ? references.reduce((a, b) => {
        const aRange = Math.abs(a.origin_price - a.pivot_price);
        const bRange = Math.abs(b.origin_price - b.pivot_price);
        return aRange > bRange ? a : b;
      })
    : null;

  // Most impulsive - only consider refs with impulsiveness data
  const refsWithImpulse = references.filter(r => r.impulsiveness !== null);
  const mostImpulsive = refsWithImpulse.length > 0
    ? refsWithImpulse.reduce((a, b) => (a.impulsiveness! > b.impulsiveness! ? a : b))
    : null;

  const bullCount = by_direction.bull?.length || 0;
  const bearCount = by_direction.bear?.length || 0;

  return (
    <div className="h-full bg-app-secondary p-4 overflow-y-auto border-t border-app-border">
      {/* Track error notification */}
      {trackError && (
        <div className="mb-3 px-3 py-2 bg-red-500/20 border border-red-500/40 rounded-lg flex items-center justify-between">
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

      <div className="grid grid-cols-5 gap-4">
        {/* References - Merged with Direction (Issue #431) */}
        <div className="bg-app-card rounded-lg p-3 border border-app-border">
          <div className="flex items-center gap-2 mb-3">
            <Layers size={14} className="text-trading-blue" />
            <h3 className="text-xs font-semibold text-app-text uppercase tracking-wider">References</h3>
          </div>
          <div className="space-y-1.5">
            {/* Sig (bin >= 8) vs Other (bin < 8) - per Issue #431/#436 */}
            {(() => {
              const sigCount = Object.entries(by_bin)
                .filter(([bin]) => parseInt(bin) >= 8)
                .reduce((sum, [, refs]) => sum + refs.length, 0);
              const otherCount = Object.entries(by_bin)
                .filter(([bin]) => parseInt(bin) < 8)
                .reduce((sum, [, refs]) => sum + refs.length, 0);

              return (
                <>
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-app-muted">Sig</span>
                    <span className="text-sm font-mono text-app-text">{sigCount}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-app-muted">Other</span>
                    <span className="text-sm font-mono text-app-text">{otherCount}</span>
                  </div>
                </>
              );
            })()}
            {/* Direction counts inline */}
            <div className="flex justify-between items-center">
              <div className="flex items-center gap-2">
                <span className="text-trading-bull">&#9650;</span>
                <span className="text-sm font-mono text-trading-bull">{bullCount}</span>
                <span className="text-trading-bear">&#9660;</span>
                <span className="text-sm font-mono text-trading-bear">{bearCount}</span>
              </div>
            </div>
            <div className="border-t border-app-border pt-1.5 mt-1.5">
              <div className="flex justify-between items-center">
                <span className="text-xs text-app-muted">Total</span>
                <span className="text-sm font-mono font-semibold text-app-text">{references.length}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Top References */}
        <div className="bg-app-card rounded-lg p-3 border border-app-border">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp size={14} className="text-trading-blue" />
            <h3 className="text-xs font-semibold text-app-text uppercase tracking-wider">Top References</h3>
          </div>
          <div className="space-y-2">
            {biggestRef && (
              <div className="text-xs">
                <div className="text-app-muted mb-0.5">Biggest</div>
                <div className="flex items-center gap-1.5">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${getBinColor(biggestRef.bin)}`}>
                    {formatMedianMultiple(biggestRef.median_multiple)}
                  </span>
                  <span className={biggestRef.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}>
                    {biggestRef.direction === 'bull' ? '\u25B2' : '\u25BC'}
                  </span>
                  <span className="font-mono text-app-text">
                    {Math.abs((biggestRef.origin_price ?? 0) - (biggestRef.pivot_price ?? 0)).toFixed(2)}
                  </span>
                </div>
              </div>
            )}
            {mostImpulsive && mostImpulsive !== biggestRef && (
              <div className="text-xs">
                <div className="text-app-muted mb-0.5">Most Impulsive</div>
                <div className="flex items-center gap-1.5">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${getBinColor(mostImpulsive.bin)}`}>
                    {formatMedianMultiple(mostImpulsive.median_multiple)}
                  </span>
                  <span className={mostImpulsive.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}>
                    {mostImpulsive.direction === 'bull' ? '\u25B2' : '\u25BC'}
                  </span>
                  <span className="font-mono text-app-text">
                    {mostImpulsive.impulsiveness?.toFixed(0)}%
                  </span>
                </div>
              </div>
            )}
            {references.length === 0 && (
              <div className="text-xs text-app-muted text-center py-2">
                No active references
              </div>
            )}
          </div>
        </div>

        {/* Filter Stats (Issue #400) */}
        <div className="bg-app-card rounded-lg p-3 border border-app-border">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Filter size={14} className="text-trading-blue" />
              <h3 className="text-xs font-semibold text-app-text uppercase tracking-wider">Filters</h3>
            </div>
            <button
              onClick={onToggleShowFiltered}
              className={`p-1 rounded transition-colors ${
                showFiltered
                  ? 'bg-trading-blue/20 text-trading-blue'
                  : 'bg-app-border text-app-muted hover:text-app-text'
              }`}
              title={showFiltered ? 'Hide filtered legs' : 'Show filtered legs'}
            >
              {showFiltered ? <Eye size={14} /> : <EyeOff size={14} />}
            </button>
          </div>
          {filter_stats ? (
            <div className="space-y-1.5">
              <div className="flex justify-between items-center">
                <span className="text-xs text-app-muted">Pass Rate</span>
                <span className="text-sm font-mono text-app-text">
                  {(filter_stats.pass_rate * 100).toFixed(0)}%
                </span>
              </div>
              <div className="w-full bg-app-border rounded-full h-1.5 mb-2">
                <div
                  className="bg-trading-bull h-1.5 rounded-full transition-all"
                  style={{ width: `${filter_stats.pass_rate * 100}%` }}
                />
              </div>
              <div className="text-[10px] text-app-muted">
                {filter_stats.valid_count} / {filter_stats.total_legs} legs passed
              </div>
              {Object.entries(filter_stats.by_reason)
                .filter(([, count]) => count > 0)
                .sort(([, a], [, b]) => b - a)
                .slice(0, 3)
                .map(([reason, count]) => {
                  const info = FILTER_REASON_LABELS[reason] || { label: reason, color: 'text-app-muted' };
                  return (
                    <div key={reason} className="flex justify-between items-center text-[10px]">
                      <span className={info.color}>{info.label}</span>
                      <span className="font-mono text-app-muted">{count}</span>
                    </div>
                  );
                })}
            </div>
          ) : (
            <div className="text-xs text-app-muted text-center py-2">
              No filter data
            </div>
          )}
        </div>

        {/* Recent Events (Issue #420, #431 multi-column redesign) */}
        <div className="bg-app-card rounded-lg p-3 border border-app-border">
          <div className="flex items-center gap-2 mb-3">
            <Zap size={14} className="text-yellow-400" />
            <h3 className="text-xs font-semibold text-app-text uppercase tracking-wider">Events</h3>
          </div>
          {/* Multi-column layout: 1-4 columns based on event count */}
          {(() => {
            // Combine lifecycle and crossing events, prioritizing lifecycle
            const allEvents: Array<{ type: 'lifecycle' | 'crossing'; event: LifecycleEvent | LevelCrossEvent }> = [
              ...lifecycleEvents.map(e => ({ type: 'lifecycle' as const, event: e })),
              ...crossingEvents.map(e => ({ type: 'crossing' as const, event: e })),
            ];
            // Take last 16 events, reversed for most recent first
            const recentEvents = allEvents.slice(-16).reverse();

            // Determine column count based on event count
            const columnClass = recentEvents.length <= 4
              ? 'columns-1'
              : recentEvents.length <= 8
                ? 'columns-2'
                : recentEvents.length <= 12
                  ? 'columns-3'
                  : 'columns-4';

            if (recentEvents.length === 0) {
              return (
                <div className="text-xs text-app-muted text-center py-2">
                  No events yet
                </div>
              );
            }

            return (
              <div className={`${columnClass} gap-x-3`}>
                {recentEvents.map((item, idx) => {
                  if (item.type === 'lifecycle') {
                    const event = item.event as LifecycleEvent;
                    const eventInfo = EVENT_TYPE_LABELS[event.event_type] || { label: event.event_type, color: 'text-app-muted', icon: 'invalidated' };
                    return (
                      <div
                        key={`lifecycle-${event.leg_id}-${event.bar_index}-${idx}`}
                        className="text-[10px] flex items-center gap-1 py-0.5 cursor-pointer hover:bg-app-border/30 rounded px-1 transition-colors break-inside-avoid"
                        onMouseEnter={() => onEventHover?.(event.leg_id)}
                        onMouseLeave={() => onEventHover?.(null)}
                      >
                        <span className={event.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}>
                          {event.direction === 'bull' ? '\u25B2' : '\u25BC'}
                        </span>
                        <span className={`${eventInfo.color} truncate`}>
                          {eventInfo.label}
                        </span>
                      </div>
                    );
                  } else {
                    const event = item.event as LevelCrossEvent;
                    return (
                      <div
                        key={`crossing-${event.leg_id}-${event.bar_index}-${idx}`}
                        className="text-[10px] flex items-center gap-1 py-0.5 cursor-pointer hover:bg-app-border/30 rounded px-1 transition-colors break-inside-avoid"
                        onMouseEnter={() => onEventHover?.(event.leg_id)}
                        onMouseLeave={() => onEventHover?.(null)}
                      >
                        <span className={event.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}>
                          {event.direction === 'bull' ? '\u25B2' : '\u25BC'}
                        </span>
                        <span className="text-app-muted truncate">
                          Crossed {(event.level_crossed ?? 0).toFixed(3)}
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

        {/* Level Crossings (Issue #416) */}
        <div className="bg-app-card rounded-lg p-3 border border-app-border">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Crosshair size={14} className="text-trading-blue" />
              <h3 className="text-xs font-semibold text-app-text uppercase tracking-wider">Crossings</h3>
            </div>
            <span className="text-[10px] text-app-muted">
              {trackedCount}/10 tracked
            </span>
          </div>
          <div className="space-y-1.5">
            {crossingEvents.length > 0 ? (
              crossingEvents.slice(-4).map((event, idx) => (
                <div key={`${event.leg_id}-${event.bar_index}-${idx}`} className="text-[10px] flex items-center gap-1.5">
                  <span className={event.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}>
                    {event.direction === 'bull' ? '\u25B2' : '\u25BC'}
                  </span>
                  <span className="font-mono text-app-text">
                    {(event.level_crossed ?? 0).toFixed(3)}
                  </span>
                  <span className={`px-1 py-0.5 rounded ${
                    event.cross_direction === 'up'
                      ? 'bg-trading-bull/20 text-trading-bull'
                      : 'bg-trading-bear/20 text-trading-bear'
                  }`}>
                    {event.cross_direction === 'up' ? '\u2191' : '\u2193'}
                  </span>
                </div>
              ))
            ) : (
              <div className="text-xs text-app-muted text-center py-2">
                {trackedCount > 0 ? 'No crossings yet' : 'Click a leg to track'}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

function getBinColor(bin: number): string {
  const colors = getBinBadgeColor(bin);
  return `${colors.bg} ${colors.text}`;
}
