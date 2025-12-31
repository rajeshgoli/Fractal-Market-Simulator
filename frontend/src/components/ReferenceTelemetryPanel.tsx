import React from 'react';
import { ReferenceStateResponse } from '../lib/api';
import { TrendingUp, TrendingDown, Layers, Activity } from 'lucide-react';

interface ReferenceTelemetryPanelProps {
  referenceState: ReferenceStateResponse | null;
}

export const ReferenceTelemetryPanel: React.FC<ReferenceTelemetryPanelProps> = ({
  referenceState,
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

  const { by_scale, by_direction, direction_imbalance, references } = referenceState;

  // Find biggest and most impulsive
  const biggestRef = references.length > 0
    ? references.reduce((a, b) => {
        const aRange = Math.abs(a.origin_price - a.pivot_price);
        const bRange = Math.abs(b.origin_price - b.pivot_price);
        return aRange > bRange ? a : b;
      })
    : null;

  const mostSalient = references.length > 0 ? references[0] : null; // Already sorted by salience

  const bullCount = by_direction.bull?.length || 0;
  const bearCount = by_direction.bear?.length || 0;
  const imbalanceRatio = bullCount > 0 && bearCount > 0
    ? Math.max(bullCount / bearCount, bearCount / bullCount).toFixed(1)
    : null;

  return (
    <div className="h-full bg-app-secondary p-4 overflow-y-auto border-t border-app-border">
      <div className="grid grid-cols-3 gap-4">
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
            {mostSalient && mostSalient !== biggestRef && (
              <div className="text-xs">
                <div className="text-app-muted mb-0.5">Most Salient</div>
                <div className="flex items-center gap-1.5">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${getScaleColor(mostSalient.scale)}`}>
                    {mostSalient.scale}
                  </span>
                  <span className={mostSalient.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}>
                    {mostSalient.direction === 'bull' ? '▲' : '▼'}
                  </span>
                  <span className="font-mono text-app-text">
                    score: {mostSalient.salience_score.toFixed(2)}
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
