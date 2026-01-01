import React from 'react';
import { ReferenceStateResponseExtended, LevelCrossEvent, LifecycleEvent } from '../lib/api';
import { TrendingUp, TrendingDown, Layers, Activity, Filter, Eye, EyeOff, Crosshair, AlertCircle, X, Zap } from 'lucide-react';

interface ReferenceTelemetryPanelProps {
  referenceState: ReferenceStateResponseExtended | null;
  showFiltered: boolean;
  onToggleShowFiltered: () => void;
  crossingEvents: LevelCrossEvent[];
  lifecycleEvents?: LifecycleEvent[];  // Recent lifecycle events for references
  trackError: string | null;
  onClearTrackError: () => void;
  trackedCount: number;
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

  const { by_scale, by_direction, direction_imbalance, references, filter_stats } = referenceState;

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
  const imbalanceRatio = bullCount > 0 && bearCount > 0
    ? Math.max(bullCount / bearCount, bearCount / bullCount).toFixed(1)
    : null;

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

      <div className="grid grid-cols-6 gap-4">
        {/* References by Scale */}
        <div className="bg-app-card rounded-lg p-3 border border-app-border">
          <div className="flex items-center gap-2 mb-3">
            <Layers size={14} className="text-trading-blue" />
            <h3 className="text-xs font-semibold text-app-text uppercase tracking-wider">References</h3>
          </div>
          <div className="space-y-1.5">
            <div className="flex justify-between items-center">
              <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-purple-600/20 text-purple-400">XL</span>
              <span className="text-sm font-mono text-app-text">{by_scale.XL?.length || 0}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-blue-600/20 text-blue-400">L</span>
              <span className="text-sm font-mono text-app-text">{by_scale.L?.length || 0}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-green-600/20 text-green-400">M</span>
              <span className="text-sm font-mono text-app-text">{by_scale.M?.length || 0}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-gray-600/20 text-gray-400">S</span>
              <span className="text-sm font-mono text-app-text">{by_scale.S?.length || 0}</span>
            </div>
            <div className="border-t border-app-border pt-1.5 mt-1.5">
              <div className="flex justify-between items-center">
                <span className="text-xs text-app-muted">Total</span>
                <span className="text-sm font-mono font-semibold text-app-text">{references.length}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Direction */}
        <div className="bg-app-card rounded-lg p-3 border border-app-border">
          <div className="flex items-center gap-2 mb-3">
            <Activity size={14} className="text-trading-blue" />
            <h3 className="text-xs font-semibold text-app-text uppercase tracking-wider">Direction</h3>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <TrendingUp size={14} className="text-trading-bull" />
                <span className="text-xs text-app-muted">Bull</span>
              </div>
              <span className="text-sm font-mono text-trading-bull">{bullCount}</span>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <TrendingDown size={14} className="text-trading-bear" />
                <span className="text-xs text-app-muted">Bear</span>
              </div>
              <span className="text-sm font-mono text-trading-bear">{bearCount}</span>
            </div>
            {direction_imbalance && (
              <div className={`mt-2 px-2 py-1 rounded text-xs font-medium text-center ${
                direction_imbalance === 'bull'
                  ? 'bg-trading-bull/20 text-trading-bull'
                  : 'bg-trading-bear/20 text-trading-bear'
              }`}>
                {direction_imbalance === 'bull' ? 'Bull' : 'Bear'}-heavy
                {imbalanceRatio && ` (${imbalanceRatio}:1)`}
              </div>
            )}
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
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${getScaleColor(biggestRef.scale)}`}>
                    {biggestRef.scale}
                  </span>
                  <span className={biggestRef.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}>
                    {biggestRef.direction === 'bull' ? '▲' : '▼'}
                  </span>
                  <span className="font-mono text-app-text">
                    {Math.abs(biggestRef.origin_price - biggestRef.pivot_price).toFixed(2)}
                  </span>
                </div>
              </div>
            )}
            {mostImpulsive && mostImpulsive !== biggestRef && (
              <div className="text-xs">
                <div className="text-app-muted mb-0.5">Most Impulsive</div>
                <div className="flex items-center gap-1.5">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${getScaleColor(mostImpulsive.scale)}`}>
                    {mostImpulsive.scale}
                  </span>
                  <span className={mostImpulsive.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}>
                    {mostImpulsive.direction === 'bull' ? '▲' : '▼'}
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

        {/* Recent Events (Issue #420) */}
        <div className="bg-app-card rounded-lg p-3 border border-app-border">
          <div className="flex items-center gap-2 mb-3">
            <Zap size={14} className="text-yellow-400" />
            <h3 className="text-xs font-semibold text-app-text uppercase tracking-wider">Events</h3>
          </div>
          <div className="space-y-1.5">
            {lifecycleEvents.length > 0 ? (
              lifecycleEvents.slice(-5).reverse().map((event, idx) => {
                const eventInfo = EVENT_TYPE_LABELS[event.event_type] || { label: event.event_type, color: 'text-app-muted', icon: 'invalidated' };
                return (
                  <div key={`lifecycle-${event.leg_id}-${event.bar_index}-${idx}`} className="text-[10px] flex items-center gap-1.5">
                    <span className={event.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}>
                      {event.direction === 'bull' ? '▲' : '▼'}
                    </span>
                    <span className={eventInfo.color}>
                      {eventInfo.label}
                    </span>
                    <span className="text-app-muted">
                      @ bar {event.bar_index}
                    </span>
                  </div>
                );
              })
            ) : crossingEvents.length > 0 ? (
              crossingEvents.slice(-4).map((event, idx) => (
                <div key={`crossing-${event.leg_id}-${event.bar_index}-${idx}`} className="text-[10px] flex items-center gap-1.5">
                  <span className={event.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}>
                    {event.direction === 'bull' ? '▲' : '▼'}
                  </span>
                  <span className="text-app-muted">Crossed</span>
                  <span className="font-mono text-app-text">
                    {event.level_crossed.toFixed(3)}
                  </span>
                  <span className={`px-1 py-0.5 rounded ${
                    event.cross_direction === 'up'
                      ? 'bg-trading-bull/20 text-trading-bull'
                      : 'bg-trading-bear/20 text-trading-bear'
                  }`}>
                    {event.cross_direction === 'up' ? '↑' : '↓'}
                  </span>
                </div>
              ))
            ) : (
              <div className="text-xs text-app-muted text-center py-2">
                No events yet
              </div>
            )}
          </div>
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
                    {event.direction === 'bull' ? '▲' : '▼'}
                  </span>
                  <span className="font-mono text-app-text">
                    {event.level_crossed.toFixed(3)}
                  </span>
                  <span className={`px-1 py-0.5 rounded ${
                    event.cross_direction === 'up'
                      ? 'bg-trading-bull/20 text-trading-bull'
                      : 'bg-trading-bear/20 text-trading-bear'
                  }`}>
                    {event.cross_direction === 'up' ? '↑' : '↓'}
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

function getScaleColor(scale: string): string {
  switch (scale) {
    case 'XL': return 'bg-purple-600/20 text-purple-400';
    case 'L': return 'bg-blue-600/20 text-blue-400';
    case 'M': return 'bg-green-600/20 text-green-400';
    case 'S': return 'bg-gray-600/20 text-gray-400';
    default: return 'bg-gray-600/20 text-gray-400';
  }
}
