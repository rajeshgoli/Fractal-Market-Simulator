import React from 'react';
import {
  SwingData,
  Direction,
  CalibrationData,
  CalibrationSwing,
  CalibrationPhase,
  SwingDisplayConfig,
  SwingScaleKey,
  ACTIVE_SWING_COUNT_OPTIONS,
} from '../types';
import { Badge } from './ui/Badge';
import { Info, GitCommit, Target, Ruler, ArrowRight, CheckCircle, ChevronLeft, ChevronRight, Play } from 'lucide-react';

interface ExplanationPanelProps {
  swing: SwingData | null;
  previousSwing?: SwingData | null;
  // Calibration props
  calibrationPhase?: CalibrationPhase;
  calibrationData?: CalibrationData | null;
  currentActiveSwing?: CalibrationSwing | null;
  currentActiveSwingIndex?: number;
  totalActiveSwings?: number;
  onNavigatePrev?: () => void;
  onNavigateNext?: () => void;
  onStartPlayback?: () => void;
  // Display config props
  displayConfig?: SwingDisplayConfig;
  filteredStats?: Record<string, { total_swings: number; active_swings: number; displayed_swings: number }>;
  onToggleScale?: (scale: SwingScaleKey) => void;
  onSetActiveSwingCount?: (count: number) => void;
}

// Safe number formatting that handles null/undefined
const formatPrice = (value: number | null | undefined, decimals: number = 2): string => {
  return (value ?? 0).toFixed(decimals);
};

export const ExplanationPanel: React.FC<ExplanationPanelProps> = ({
  swing,
  previousSwing,
  calibrationPhase,
  calibrationData,
  currentActiveSwing,
  currentActiveSwingIndex = 0,
  totalActiveSwings = 0,
  onNavigatePrev,
  onNavigateNext,
  onStartPlayback,
  displayConfig,
  filteredStats,
  onToggleScale,
  onSetActiveSwingCount,
}) => {
  // Show calibration report when calibrated
  if (calibrationPhase === CalibrationPhase.CALIBRATED && calibrationData) {
    const thresholds = calibrationData.scale_thresholds;
    const scaleOrder: SwingScaleKey[] = ['XL', 'L', 'M', 'S'];
    // Use filteredStats if available, otherwise fall back to calibration stats
    const statsToDisplay = filteredStats || Object.fromEntries(
      scaleOrder.map(scale => [scale, {
        total_swings: calibrationData.stats_by_scale[scale]?.total_swings || 0,
        active_swings: calibrationData.stats_by_scale[scale]?.active_swings || 0,
        displayed_swings: calibrationData.stats_by_scale[scale]?.active_swings || 0,
      }])
    );

    return (
      <div className="h-full bg-app-secondary border-t border-app-border flex flex-col font-sans text-sm">
        {/* Panel Header */}
        <div className="flex items-center gap-3 px-4 py-2 border-b border-app-border bg-app-bg/40">
          <div className="flex items-center gap-2 text-app-text font-semibold tracking-wider uppercase">
            <CheckCircle size={16} className="text-trading-bull" />
            <span>Calibration Complete</span>
          </div>
          <div className="h-4 w-px bg-app-border mx-2"></div>
          <span className="text-xs text-app-muted">
            {calibrationData.calibration_bar_count.toLocaleString()} bars
          </span>
        </div>

        {/* Content Grid */}
        <div className="flex-1 grid grid-cols-1 md:grid-cols-4 divide-y md:divide-y-0 md:divide-x divide-app-border/50 overflow-hidden">
          {/* Column 1: Scale Filters */}
          <div className="p-4 flex flex-col justify-center">
            <span className="text-xs text-app-muted font-medium uppercase tracking-wider block mb-3">
              Scale Filters
            </span>
            <div className="flex flex-wrap gap-2">
              {scaleOrder.map(scale => {
                const isEnabled = displayConfig?.enabledScales.has(scale) ?? (scale !== 'S');
                return (
                  <label
                    key={scale}
                    className={`flex items-center gap-1.5 px-2 py-1 rounded border cursor-pointer transition-colors ${
                      isEnabled
                        ? 'bg-trading-blue/20 border-trading-blue text-trading-blue'
                        : 'bg-app-card border-app-border text-app-muted hover:border-app-text/30'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isEnabled}
                      onChange={() => onToggleScale?.(scale)}
                      className="sr-only"
                    />
                    <span className={`w-3 h-3 rounded-sm border flex items-center justify-center ${
                      isEnabled ? 'bg-trading-blue border-trading-blue' : 'border-app-muted'
                    }`}>
                      {isEnabled && <span className="text-white text-[10px]">✓</span>}
                    </span>
                    <span className="text-xs font-semibold">{scale}</span>
                  </label>
                );
              })}
            </div>
            {/* Active swings dropdown */}
            <div className="mt-4">
              <label className="text-xs text-app-muted block mb-1">Active swings to show:</label>
              <select
                value={displayConfig?.activeSwingCount ?? 2}
                onChange={(e) => onSetActiveSwingCount?.(parseInt(e.target.value, 10))}
                className="bg-app-card border border-app-border rounded px-2 py-1 text-sm text-app-text focus:outline-none focus:border-trading-blue"
              >
                {ACTIVE_SWING_COUNT_OPTIONS.map(n => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Column 2: Calibration Report */}
          <div className="p-4 flex flex-col justify-center">
            <span className="text-xs text-app-muted font-medium uppercase tracking-wider block mb-3">
              Calibration Report
            </span>
            <div className="space-y-2">
              {scaleOrder.map(scale => {
                const scaleStat = statsToDisplay[scale];
                const isEnabled = displayConfig?.enabledScales.has(scale) ?? (scale !== 'S');
                if (!scaleStat) return null;
                return (
                  <div
                    key={scale}
                    className={`flex items-center justify-between ${!isEnabled ? 'opacity-40' : ''}`}
                  >
                    <div className="flex items-center gap-2">
                      <Badge variant="neutral" className="min-w-[2rem] justify-center text-xs">{scale}</Badge>
                      <span className="text-app-text font-mono text-xs">{scaleStat.total_swings} swings</span>
                    </div>
                    <span className="text-xs text-trading-blue">
                      ({scaleStat.displayed_swings} shown)
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Column 3: Scale Thresholds */}
          <div className="p-4 flex flex-col justify-center">
            <span className="text-xs text-app-muted font-medium uppercase tracking-wider block mb-3">
              Scale Thresholds
            </span>
            <div className="space-y-2">
              {scaleOrder.map(scale => {
                const threshold = thresholds[scale];
                const isEnabled = displayConfig?.enabledScales.has(scale) ?? (scale !== 'S');
                return (
                  <div
                    key={scale}
                    className={`flex items-center justify-between ${!isEnabled ? 'opacity-40' : ''}`}
                  >
                    <Badge variant="neutral" className="min-w-[2rem] justify-center text-xs">{scale}</Badge>
                    <span className="font-mono text-app-text text-xs">
                      {threshold === 0 ? 'All sizes' : `≥ ${threshold} pts`}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Column 4: Active Swing Navigation + Start Button */}
          <div className="p-4 flex flex-col justify-center items-center gap-3">
            {totalActiveSwings > 0 ? (
              <>
                {/* Navigation */}
                <div className="flex items-center gap-3">
                  <button
                    onClick={onNavigatePrev}
                    className="p-1.5 rounded bg-app-card border border-app-border hover:bg-app-bg transition-colors"
                    title="Previous swing ([)"
                  >
                    <ChevronLeft size={16} />
                  </button>
                  <div className="text-center">
                    <div className="text-base font-mono font-semibold text-app-text">
                      {currentActiveSwingIndex + 1} / {totalActiveSwings}
                    </div>
                    {currentActiveSwing && (
                      <div className="flex gap-1 mt-0.5 justify-center">
                        <Badge variant="neutral" className="text-[10px] px-1">{currentActiveSwing.scale}</Badge>
                        <Badge
                          variant={currentActiveSwing.direction === 'bull' ? 'bull' : 'bear'}
                          className="text-[10px] px-1"
                        >
                          {currentActiveSwing.direction.toUpperCase()}
                        </Badge>
                      </div>
                    )}
                  </div>
                  <button
                    onClick={onNavigateNext}
                    className="p-1.5 rounded bg-app-card border border-app-border hover:bg-app-bg transition-colors"
                    title="Next swing (])"
                  >
                    <ChevronRight size={16} />
                  </button>
                </div>

                {/* Start Playback Button */}
                <button
                  onClick={onStartPlayback}
                  className="flex items-center gap-2 px-4 py-1.5 bg-trading-blue text-white font-semibold rounded hover:bg-blue-600 transition-colors text-sm"
                >
                  <Play size={16} />
                  Start Playback
                </button>
                <span className="text-[10px] text-app-muted">Press Space or Enter</span>
              </>
            ) : (
              <div className="text-center">
                <p className="text-app-muted text-xs mb-3">No active swings for selected scales</p>
                <button
                  onClick={onStartPlayback}
                  className="flex items-center gap-2 px-4 py-1.5 bg-trading-blue text-white font-semibold rounded hover:bg-blue-600 transition-colors text-sm"
                >
                  <Play size={16} />
                  Start Playback
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Current swing details (dimmed footer) */}
        {currentActiveSwing && (
          <div className="px-4 py-2 border-t border-app-border/30 bg-app-bg/20">
            <div className="flex items-center gap-4 text-xs text-app-muted">
              <span>
                <span className="text-trading-bull">H:</span> {formatPrice(currentActiveSwing.high_price)} (bar {currentActiveSwing.high_bar_index})
              </span>
              <span>
                <span className="text-trading-bear">L:</span> {formatPrice(currentActiveSwing.low_price)} (bar {currentActiveSwing.low_bar_index})
              </span>
              <span>
                <span className="text-app-text">Size:</span> {formatPrice(currentActiveSwing.size)} pts
              </span>
            </div>
          </div>
        )}
      </div>
    );
  }

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

        {/* Column 3: Trigger Explanation / Separation / Context */}
        <div className="p-4 flex flex-col justify-center space-y-4">
          {swing.triggerExplanation ? (
            <div className="space-y-3">
              <span className="text-xs text-app-muted font-medium uppercase tracking-wider block">
                Trigger Explanation
              </span>
              <div className="bg-app-card/30 rounded border border-app-border/50 p-3">
                <pre className="text-xs text-app-text whitespace-pre-wrap font-mono leading-relaxed">
                  {swing.triggerExplanation}
                </pre>
              </div>
            </div>
          ) : swing.isAnchor ? (
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
