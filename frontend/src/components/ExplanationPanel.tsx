import React from 'react';
import { SwingData, Direction } from '../types';
import { Badge } from './ui/Badge';
import { Info, GitCommit, Target, Ruler, ArrowRight } from 'lucide-react';

interface ExplanationPanelProps {
  swing: SwingData | null;
  previousSwing?: SwingData | null;
}

// Safe number formatting that handles null/undefined
const formatPrice = (value: number | null | undefined, decimals: number = 2): string => {
  return (value ?? 0).toFixed(decimals);
};

export const ExplanationPanel: React.FC<ExplanationPanelProps> = ({ swing, previousSwing }) => {
  if (!swing) {
    return (
      <div className="h-full w-full flex flex-col items-center justify-center text-app-muted border-t border-app-border bg-app-secondary p-6">
        <Info className="w-8 h-8 mb-2 opacity-50" />
        <p className="text-sm text-center">
          Advance playback to a SWING_FORMED event to see detection details.
        </p>
      </div>
    );
  }

  const isBull = swing.direction.toUpperCase() === Direction.BULL;
  const priceColor = isBull ? 'text-trading-bull' : 'text-trading-bear';

  return (
    <div className="h-full bg-app-secondary border-t border-app-border flex flex-col font-sans text-sm">
      {/* Panel Header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-app-border bg-app-bg/40">
        <div className="flex items-center gap-2 text-app-text font-semibold tracking-wider uppercase">
          <GitCommit size={16} className="text-trading-purple" />
          <span>Swing Formed</span>
        </div>
        <div className="h-4 w-px bg-app-border mx-2"></div>
        <div className="flex gap-2">
          <Badge variant="neutral" className="min-w-[2rem] justify-center">{swing.scale}</Badge>
          <Badge variant={isBull ? 'bull' : 'bear'}>{swing.direction.toUpperCase()}</Badge>
        </div>
      </div>

      {/* Content Grid */}
      <div className="flex-1 grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-app-border/50 overflow-hidden">
        {/* Column 1: Endpoints */}
        <div className="p-4 flex flex-col justify-center space-y-4">
          <div className="space-y-3">
            {/* High Point */}
            <div className="flex flex-col">
              <div className="flex justify-between items-end mb-1">
                <span className="text-xs text-app-muted font-medium uppercase tracking-wider">High</span>
                <span className="font-mono text-[10px] text-app-muted bg-app-card px-1.5 py-0.5 rounded border border-app-border/50">
                  Bar {swing.highBar}
                </span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-lg font-mono tabular-nums text-trading-bull tracking-tight">
                  {formatPrice(swing.highPrice)}
                </span>
                <span className="text-xs text-app-muted tabular-nums">{swing.highTime}</span>
              </div>
            </div>

            <div className="h-px bg-app-border/30 w-full"></div>

            {/* Low Point */}
            <div className="flex flex-col">
              <div className="flex justify-between items-end mb-1">
                <span className="text-xs text-app-muted font-medium uppercase tracking-wider">Low</span>
                <span className="font-mono text-[10px] text-app-muted bg-app-card px-1.5 py-0.5 rounded border border-app-border/50">
                  Bar {swing.lowBar}
                </span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-lg font-mono tabular-nums text-trading-bear tracking-tight">
                  {formatPrice(swing.lowPrice)}
                </span>
                <span className="text-xs text-app-muted tabular-nums">{swing.lowTime}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Column 2: Size & Logic */}
        <div className="p-4 flex flex-col justify-center space-y-4">
          <div>
            <span className="text-xs text-app-muted font-medium uppercase tracking-wider block mb-2">Size & Scale</span>
            <div className="flex items-baseline gap-3">
              <span className={`text-2xl font-mono tabular-nums font-medium ${priceColor}`}>
                {formatPrice(swing.size)} <span className="text-sm text-app-muted font-sans">pts</span>
              </span>
              <span className="text-sm text-app-muted tabular-nums">
                ({formatPrice(swing.sizePct)}%)
              </span>
            </div>
          </div>

          {swing.scaleReason && (
            <div className="bg-app-card/30 rounded border border-app-border/50 p-3">
              <div className="flex items-center gap-2 mb-1.5">
                <Target size={14} className="text-trading-blue" />
                <span className="text-xs font-bold text-app-text">Why {swing.scale}?</span>
              </div>
              <p className="text-xs text-app-muted">{swing.scaleReason}</p>
            </div>
          )}
        </div>

        {/* Column 3: Separation / Context */}
        <div className="p-4 flex flex-col justify-center space-y-4">
          {swing.isAnchor ? (
            <div className="bg-trading-purple/20 text-trading-purple rounded border border-trading-purple/30 p-4 text-center">
              <span className="text-sm font-semibold">Anchor Swing</span>
              <p className="text-xs mt-1 opacity-80">Largest swing in calibration window</p>
            </div>
          ) : swing.separation ? (
            <div className="space-y-3">
              <span className="text-xs text-app-muted font-medium uppercase tracking-wider block">
                Separation from Previous
              </span>

              <div>
                <div className="flex justify-between text-xs mb-1.5">
                  <span className="text-app-muted">Fib Distance</span>
                  <span className="font-mono text-trading-blue">{formatPrice(swing.separation.distanceFib, 3)}</span>
                </div>
                <div className="relative h-2 bg-app-bg rounded-full overflow-hidden border border-app-border/50">
                  {/* Marker for min requirement */}
                  <div
                    className="absolute top-0 bottom-0 w-0.5 bg-app-muted/50 z-10"
                    style={{ left: `${((swing.separation.minimumFib ?? 0) * 100)}%` }}
                  ></div>
                  {/* Fill */}
                  <div
                    className="absolute top-0 left-0 bottom-0 bg-trading-purple"
                    style={{ width: `${Math.min((swing.separation.distanceFib ?? 0) * 100, 100)}%` }}
                  ></div>
                </div>
                <div className="flex justify-between text-[10px] text-app-muted mt-1">
                  <span>0.0</span>
                  <span>Min: {formatPrice(swing.separation.minimumFib, 3)}</span>
                  <span>1.0</span>
                </div>
              </div>

              {swing.separation.fromSwingId && (
                <div className="mt-2 pt-3 border-t border-app-border/30">
                  <div className="flex items-center gap-2 text-xs text-app-muted mb-1">
                    <Ruler size={12} />
                    <span>Reference Swing</span>
                  </div>
                  <div className="flex items-center gap-2 text-app-muted/70 text-xs">
                    <ArrowRight size={12} />
                    <code className="bg-app-bg px-1 rounded border border-app-border/50">
                      {swing.separation.fromSwingId.substring(0, 8)}...
                    </code>
                    <span className="italic opacity-50">(dimmed on chart)</span>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-xs text-app-muted text-center py-4">
              No separation data available
            </div>
          )}
        </div>
      </div>

      {/* Previous Swing (dimmed) */}
      {previousSwing && (
        <div className="px-4 py-2 border-t border-app-border/30 bg-app-bg/20">
          <div className="flex items-center gap-3 opacity-60">
            <span className="text-[10px] text-trading-orange uppercase tracking-wider">Previous</span>
            <Badge variant="neutral" className="text-[10px]">{previousSwing.scale}</Badge>
            <Badge variant={previousSwing.direction.toUpperCase() === Direction.BULL ? 'bull' : 'bear'} className="text-[10px]">
              {previousSwing.direction.toUpperCase()}
            </Badge>
            <span className="text-xs text-app-muted font-mono tabular-nums">
              {formatPrice(previousSwing.highPrice)} / {formatPrice(previousSwing.lowPrice)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
