import React, { useState, useRef, useImperativeHandle, forwardRef, useMemo } from 'react';
import { ChevronDown, ChevronRight, Settings, RotateCcw, Activity, Loader, Filter, Eye, EyeOff } from 'lucide-react';
import {
  ReferenceConfig,
  TelemetryPanelResponse,
  FilterStats,
  DEFAULT_REFERENCE_CONFIG,
} from '../lib/api';
import { FeedbackForm } from './FeedbackForm';
import type { FeedbackContext, DagContext } from './FeedbackForm';
import { ReplayEvent } from '../lib/api';
import { AttachableItem } from './DAGStatePanel';
import { getBinBadgeColor } from '../utils/binUtils';
import { Toggle } from './ui/Toggle';

// ============================================================================
// Reference Config Panel (Issue #424, #429, #444)
// ============================================================================

export interface ReferenceConfigPanelHandle {
  reset: () => void;
}

interface ReferenceConfigPanelProps {
  config: ReferenceConfig;
  onConfigUpdate: (config: ReferenceConfig) => void | Promise<void>;
  hideHeader?: boolean;
}

// Discrete Fib values for formation threshold slider
// 0 = "Off" (least restrictive - every leg is formed)
// Higher values = more restrictive (need more retracement to form)
const FORMATION_FIB_VALUES = [0, 0.236, 0.382, 0.5, 0.618];

// Find nearest value in array
function findNearestIndex(value: number, values: number[]): number {
  let nearestIndex = 0;
  let minDiff = Math.abs(value - values[0]);
  for (let i = 1; i < values.length; i++) {
    const diff = Math.abs(value - values[i]);
    if (diff < minDiff) {
      minDiff = diff;
      nearestIndex = i;
    }
  }
  return nearestIndex;
}

// Tooltip definitions for each parameter
const TOOLTIPS = {
  range_weight: "Rank by leg size. Larger legs score higher.",
  impulse_weight: "Rank by move speed. Fast, impulsive moves score higher.",
  recency_weight: "Rank by age. Recent legs score higher.",
  depth_weight: "Rank by hierarchy depth. Root-level legs score higher.",
  counter_weight: "Rank by counter-trend defense. Legs with larger counter-trend ranges score higher.",
  range_counter_weight: "Rank by structural importance: leg size \u00d7 counter-trend defense. Must be big AND defended.",
  formation_fib_threshold: "Retracement required before leg forms. Higher = stricter formation (only clear reversals).",
  pivot_breach_tolerance: "How far price can breach pivot before leg is invalidated. Higher = more tolerant.",
  top_n: "Maximum number of reference legs to display. Lower = less clutter.",
};

const ReferenceConfigPanelInner = forwardRef<ReferenceConfigPanelHandle, ReferenceConfigPanelProps>(({
  config,
  onConfigUpdate,
  hideHeader = false,
}, ref) => {
  // Local state for sliders
  const [localConfig, setLocalConfig] = useState<ReferenceConfig>(config);
  const [isUpdating, setIsUpdating] = useState(false);
  const hasAppliedRef = React.useRef(false);

  // Track if config has changes from server config (#436, #442, #444, #454: unified weights)
  const hasChanges = useMemo(() => {
    return (
      localConfig.range_weight !== config.range_weight ||
      localConfig.impulse_weight !== config.impulse_weight ||
      localConfig.recency_weight !== config.recency_weight ||
      localConfig.depth_weight !== config.depth_weight ||
      localConfig.counter_weight !== config.counter_weight ||
      localConfig.range_counter_weight !== config.range_counter_weight ||
      localConfig.formation_fib_threshold !== config.formation_fib_threshold ||
      localConfig.pivot_breach_tolerance !== config.pivot_breach_tolerance ||
      localConfig.top_n !== config.top_n
    );
  }, [localConfig, config]);

  // Reset handler exposed via ref
  useImperativeHandle(ref, () => ({
    reset: () => {
      setLocalConfig(DEFAULT_REFERENCE_CONFIG);
    },
  }));

  // Update local config when prop changes (after successful apply)
  React.useEffect(() => {
    if (hasAppliedRef.current) {
      setLocalConfig(config);
      hasAppliedRef.current = false;
    }
  }, [config]);

  const handleSliderChange = (key: keyof ReferenceConfig, value: number) => {
    setLocalConfig(prev => ({ ...prev, [key]: value }));
  };

  const handleApply = async () => {
    setIsUpdating(true);
    try {
      hasAppliedRef.current = true;
      await onConfigUpdate(localConfig);
    } finally {
      setIsUpdating(false);
    }
  };

  // Get orange gradient color for breach tolerance (intensifies toward max)
  const getBreachColor = (value: number, max: number): string => {
    // 0 = blue (safe), max = orange (caution)
    const ratio = max > 0 ? value / max : 0;
    const r = Math.round(59 + ratio * (249 - 59));
    const g = Math.round(130 + ratio * (115 - 130));
    const b = Math.round(246 + ratio * (22 - 246));
    return `rgb(${r}, ${g}, ${b})`;
  };

  // Render discrete Fib slider with stop labels for Formation (#444)
  const renderFormationSlider = () => {
    const value = localConfig.formation_fib_threshold ?? FORMATION_FIB_VALUES[1];
    const sliderIndex = findNearestIndex(value, FORMATION_FIB_VALUES);
    const displayValue = value === 0 ? 'Off' : value.toFixed(3);

    // Calculate fill percentage for gradient effect
    const fillPercent = (sliderIndex / (FORMATION_FIB_VALUES.length - 1)) * 100;
    const trackStyle = {
      background: `linear-gradient(to right, rgb(59, 130, 246) 0%, rgb(59, 130, 246) ${fillPercent}%, rgb(55, 65, 81) ${fillPercent}%, rgb(55, 65, 81) 100%)`,
    };

    return (
      <div className="space-y-0.5">
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-app-muted whitespace-nowrap w-[52px] shrink-0" title={TOOLTIPS.formation_fib_threshold}>Threshold</span>
          <input
            type="range"
            min={0}
            max={FORMATION_FIB_VALUES.length - 1}
            step={1}
            value={sliderIndex}
            onChange={(e) => handleSliderChange('formation_fib_threshold', FORMATION_FIB_VALUES[parseInt(e.target.value)])}
            className="flex-1 min-w-0 h-1.5 rounded-lg appearance-none cursor-pointer"
            style={trackStyle}
            disabled={isUpdating}
          />
          <span className="text-[10px] font-mono min-w-[36px] text-right text-app-text shrink-0">
            {displayValue}
          </span>
        </div>
        {/* Endpoint labels */}
        <div className="flex items-center gap-1 text-[8px] text-app-muted">
          <div className="w-[52px] shrink-0"></div>
          <span>Off</span>
          <span className="flex-1"></span>
          <span>.618</span>
          <div className="min-w-[36px] shrink-0"></div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {!hideHeader && (
        <div className="flex items-center gap-2 mb-2">
          <Settings size={14} className="text-trading-blue" />
          <h3 className="text-xs font-semibold text-app-text uppercase tracking-wider">Reference Config</h3>
        </div>
      )}

      {/* FORMATION Section (#444) */}
      <div className="space-y-2">
        <div className="text-[10px] font-medium text-app-muted uppercase tracking-wider">Formation</div>
        {renderFormationSlider()}
      </div>

      {/* PIVOT BREACH Section (#454: renamed from Origin Breach) - continuous slider 0-0.3, orange gradient */}
      <div className="space-y-2">
        <div className="text-[10px] font-medium text-app-muted uppercase tracking-wider">Pivot Breach</div>
        {(() => {
          const breachValue = localConfig.pivot_breach_tolerance ?? 0;
          const fillPercent = (breachValue / 0.3) * 100;
          const fillColor = getBreachColor(breachValue, 0.3);
          const trackStyle = {
            background: `linear-gradient(to right, ${fillColor} 0%, ${fillColor} ${fillPercent}%, rgb(55, 65, 81) ${fillPercent}%, rgb(55, 65, 81) 100%)`,
          };
          return (
            <div className="flex items-center gap-1">
              <span className="text-[10px] text-app-muted whitespace-nowrap w-[52px] shrink-0" title={TOOLTIPS.pivot_breach_tolerance}>Tolerance</span>
              <input
                type="range"
                min={0}
                max={0.3}
                step={0.01}
                value={breachValue}
                onChange={(e) => handleSliderChange('pivot_breach_tolerance', parseFloat(e.target.value))}
                className="flex-1 min-w-0 h-1.5 rounded-lg appearance-none cursor-pointer"
                style={trackStyle}
                disabled={isUpdating}
              />
              <span className="text-[10px] font-mono min-w-[36px] text-right text-app-text shrink-0">
                {breachValue.toFixed(2)}
              </span>
            </div>
          );
        })()}
      </div>

      {/* SALIENCE WEIGHTS Section (#436, #442, #444: unified additive formula) */}
      <div className="space-y-2">
        <div className="text-[10px] font-medium text-app-muted uppercase tracking-wider">Salience Weights</div>
        <SliderRow
          label="Range"
          value={localConfig.range_weight ?? 0.8}
          onChange={(v) => handleSliderChange('range_weight', v)}
          min={0}
          max={1}
          step={0.1}
          disabled={isUpdating}
          tooltip={TOOLTIPS.range_weight}
        />
        <SliderRow
          label="Counter"
          value={localConfig.counter_weight ?? 0.0}
          onChange={(v) => handleSliderChange('counter_weight', v)}
          min={0}
          max={1}
          step={0.1}
          disabled={isUpdating}
          tooltip={TOOLTIPS.counter_weight}
        />
        <SliderRow
          label="Rng×Ctr"
          value={localConfig.range_counter_weight ?? 0.0}
          onChange={(v) => handleSliderChange('range_counter_weight', v)}
          min={0}
          max={1}
          step={0.1}
          disabled={isUpdating}
          tooltip={TOOLTIPS.range_counter_weight}
        />
        <SliderRow
          label="Impulse"
          value={localConfig.impulse_weight ?? 0.0}
          onChange={(v) => handleSliderChange('impulse_weight', v)}
          min={0}
          max={1}
          step={0.1}
          disabled={isUpdating}
          tooltip={TOOLTIPS.impulse_weight}
        />
        <SliderRow
          label="Depth"
          value={localConfig.depth_weight ?? 0.0}
          onChange={(v) => handleSliderChange('depth_weight', v)}
          min={0}
          max={1}
          step={0.1}
          disabled={isUpdating}
          tooltip={TOOLTIPS.depth_weight}
        />
        <SliderRow
          label="Recency"
          value={localConfig.recency_weight ?? 0.4}
          onChange={(v) => handleSliderChange('recency_weight', v)}
          min={0}
          max={1}
          step={0.1}
          disabled={isUpdating}
          tooltip={TOOLTIPS.recency_weight}
        />
      </div>

      {/* DISPLAY Section (#444) */}
      <div className="space-y-2">
        <div className="text-[10px] font-medium text-app-muted uppercase tracking-wider">Display</div>
        <SliderRow
          label="Show top"
          value={localConfig.top_n ?? 5}
          onChange={(v) => handleSliderChange('top_n', Math.round(v))}
          min={1}
          max={20}
          step={1}
          formatValue={(v) => String(Math.round(v))}
          disabled={isUpdating}
          tooltip={TOOLTIPS.top_n}
        />
      </div>

      {/* Apply Button */}
      <button
        onClick={handleApply}
        disabled={!hasChanges || isUpdating}
        className={`w-full py-2 text-xs font-medium rounded transition-colors flex items-center justify-center gap-2 ${
          hasChanges && !isUpdating
            ? 'bg-trading-blue text-white hover:bg-blue-600'
            : 'bg-app-border text-app-muted cursor-not-allowed'
        }`}
      >
        {isUpdating ? (
          <>
            <Loader size={12} className="animate-spin" />
            Applying...
          </>
        ) : (
          'Apply'
        )}
      </button>
    </div>
  );
});

ReferenceConfigPanelInner.displayName = 'ReferenceConfigPanel';

export const ReferenceConfigPanel = ReferenceConfigPanelInner;

// Slider row component (#444: compact layout, color fill effect)
interface SliderRowProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step: number;
  formatValue?: (value: number) => string;
  disabled?: boolean;
  tooltip?: string;
  color?: string; // Custom color for fill (defaults to trading-blue)
}

const SliderRow: React.FC<SliderRowProps> = ({
  label,
  value,
  onChange,
  min,
  max,
  step,
  formatValue = (v) => v.toFixed(1),
  disabled = false,
  tooltip,
  color = 'rgb(59, 130, 246)', // trading-blue
}) => {
  // Calculate fill percentage for gradient effect
  const fillPercent = ((value - min) / (max - min)) * 100;
  const trackStyle = {
    background: `linear-gradient(to right, ${color} 0%, ${color} ${fillPercent}%, rgb(55, 65, 81) ${fillPercent}%, rgb(55, 65, 81) 100%)`,
  };

  return (
    <div className="flex items-center gap-1">
      <span
        className={`text-[10px] whitespace-nowrap w-[52px] shrink-0 ${disabled ? 'text-app-muted/50' : 'text-app-muted'}`}
        title={tooltip}
      >
        {label}
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className={`flex-1 min-w-0 h-1.5 rounded-lg appearance-none ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
        style={trackStyle}
        disabled={disabled}
      />
      <span className={`text-[10px] font-mono min-w-[36px] text-right shrink-0 ${disabled ? 'text-app-muted/50' : 'text-app-text'}`}>
        {formatValue(value)}
      </span>
    </div>
  );
};

// ============================================================================
// Reference Stats Panel (Compact version for sidebar)
// ============================================================================

interface ReferenceStatsPanelProps {
  telemetryData: TelemetryPanelResponse | null;
  isLoading?: boolean;
}

const ReferenceStatsPanel: React.FC<ReferenceStatsPanelProps> = ({
  telemetryData,
  isLoading = false,
}) => {
  if (isLoading || !telemetryData) {
    return (
      <div className="text-xs text-app-muted text-center py-4">
        {isLoading ? 'Loading...' : 'No telemetry data'}
      </div>
    );
  }

  const { counts_by_bin, total_count, bull_count, bear_count, direction_imbalance, imbalance_ratio } = telemetryData;

  // Group bins into categories: 0-7 (Small), 8 (Sig), 9 (Large), 10 (XL)
  const smallCount = Object.entries(counts_by_bin)
    .filter(([bin]) => parseInt(bin) <= 7)
    .reduce((sum, [, count]) => sum + count, 0);
  const sigCount = counts_by_bin[8] || 0;
  const largeCount = counts_by_bin[9] || 0;
  const xlCount = counts_by_bin[10] || 0;

  const binCategories = [
    { label: '25x+', count: xlCount, bin: 10 },
    { label: '10-25x', count: largeCount, bin: 9 },
    { label: '5-10x', count: sigCount, bin: 8 },
    { label: '<5x', count: smallCount, bin: 7 },
  ];

  return (
    <div className="space-y-3">
      {/* Counts by Bin Category */}
      <div className="grid grid-cols-4 gap-1">
        {binCategories.map(({ label, count, bin }) => {
          const binColor = getBinBadgeColor(bin);
          return (
            <div key={label} className="text-center">
              <span className={`text-[9px] font-medium px-1.5 py-0.5 rounded ${binColor.bg} ${binColor.text}`}>
                {label}
              </span>
              <div className="text-xs font-mono text-app-text mt-1">{count}</div>
            </div>
          );
        })}
      </div>

      {/* Direction */}
      <div className="flex justify-between items-center pt-2 border-t border-app-border">
        <div className="flex items-center gap-2">
          <span className="text-xs text-trading-bull">Bull: {bull_count}</span>
          <span className="text-xs text-app-muted">/</span>
          <span className="text-xs text-trading-bear">Bear: {bear_count}</span>
        </div>
        {direction_imbalance && (
          <span className={`text-[10px] px-1.5 py-0.5 rounded ${
            direction_imbalance === 'bull'
              ? 'bg-trading-bull/20 text-trading-bull'
              : 'bg-trading-bear/20 text-trading-bear'
          }`}>
            {direction_imbalance === 'bull' ? 'Bull' : 'Bear'}-heavy
            {imbalance_ratio && ` (${imbalance_ratio})`}
          </span>
        )}
      </div>

      {/* Total */}
      <div className="flex justify-between items-center">
        <span className="text-xs text-app-muted">Total References</span>
        <span className="text-sm font-mono font-semibold text-app-text">{total_count}</span>
      </div>
    </div>
  );
};

// ============================================================================
// Filters Panel (Issue #445 - moved from bottom panel)
// ============================================================================

// Filter reason display names and colors (#454: origin_breached removed)
const FILTER_REASON_LABELS: Record<string, { label: string; color: string }> = {
  not_formed: { label: 'Not Formed', color: 'text-yellow-400' },
  pivot_breached: { label: 'Pivot Breached', color: 'text-red-400' },
  completed: { label: 'Completed', color: 'text-blue-400' },
  cold_start: { label: 'Cold Start', color: 'text-gray-400' },
};

interface FiltersPanelProps {
  filterStats: FilterStats | null;
  showFiltered: boolean;
  onToggleShowFiltered: () => void;
}

const FiltersPanel: React.FC<FiltersPanelProps> = ({
  filterStats,
  showFiltered,
  onToggleShowFiltered,
}) => {
  if (!filterStats) {
    return (
      <div className="text-xs text-app-muted text-center py-4">
        No filter data
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Show Filtered Toggle - DAG linger toggle style */}
      <div className="flex items-center justify-between p-2 bg-app-card rounded-lg border border-app-border">
        <div className="flex items-center gap-2">
          {showFiltered ? (
            <Eye size={14} className="text-trading-blue" />
          ) : (
            <EyeOff size={14} className="text-app-muted" />
          )}
          <span className={`text-xs ${showFiltered ? 'text-app-text' : 'text-app-muted'}`}>
            Show Filtered
          </span>
        </div>
        <Toggle
          checked={showFiltered}
          onChange={onToggleShowFiltered}
          id="toggle-show-filtered"
        />
      </div>

      {/* Pass Rate */}
      <div className="space-y-1.5">
        <div className="flex justify-between items-center">
          <span className="text-xs text-app-muted">Pass Rate</span>
          <span className="text-sm font-mono text-app-text">
            {(filterStats.pass_rate * 100).toFixed(0)}%
          </span>
        </div>
        <div className="w-full bg-app-border rounded-full h-1.5">
          <div
            className="bg-trading-bull h-1.5 rounded-full transition-all"
            style={{ width: `${filterStats.pass_rate * 100}%` }}
          />
        </div>
        <div className="text-[10px] text-app-muted">
          {filterStats.valid_count} / {filterStats.total_legs} legs passed
        </div>
      </div>

      {/* Filter Reasons */}
      <div className="space-y-1">
        {Object.entries(filterStats.by_reason)
          .filter(([, count]) => count > 0)
          .sort(([, a], [, b]) => b - a)
          .map(([reason, count]) => {
            const info = FILTER_REASON_LABELS[reason] || { label: reason, color: 'text-app-muted' };
            return (
              <div key={reason} className="flex justify-between items-center text-xs">
                <span className={info.color}>{info.label}</span>
                <span className="font-mono text-app-muted">{count}</span>
              </div>
            );
          })}
      </div>
    </div>
  );
};

// ============================================================================
// Reference Sidebar (Issue #424, #445)
// ============================================================================

interface ReferenceSidebarProps {
  // Reference Config
  referenceConfig?: ReferenceConfig;
  onReferenceConfigUpdate?: (config: ReferenceConfig) => void | Promise<void>;

  // Feedback (same as DAG Sidebar)
  showFeedback?: boolean;
  currentPlaybackBar?: number;
  feedbackContext?: FeedbackContext;
  onFeedbackFocus?: () => void;
  onFeedbackBlur?: () => void;
  onPausePlayback?: () => void;
  screenshotTargetRef?: React.RefObject<HTMLElement | null>;

  // Feedback attachments
  attachedItems?: AttachableItem[];
  onDetachItem?: (item: AttachableItem) => void;
  onClearAttachments?: () => void;
  isLingering?: boolean;
  lingerEvent?: ReplayEvent;
  dagContext?: DagContext;

  // Telemetry (Reference Stats)
  telemetryData?: TelemetryPanelResponse;

  // Filters (Issue #445 - moved from bottom panel)
  filterStats?: FilterStats | null;
  showFiltered?: boolean;
  onToggleShowFiltered?: () => void;

  // Reset
  onResetDefaults?: () => void;
  className?: string;
}

export const ReferenceSidebar: React.FC<ReferenceSidebarProps> = ({
  referenceConfig,
  onReferenceConfigUpdate,
  showFeedback = false,
  currentPlaybackBar,
  feedbackContext,
  onFeedbackFocus,
  onFeedbackBlur,
  onPausePlayback,
  screenshotTargetRef,
  attachedItems = [],
  onDetachItem = () => {},
  onClearAttachments = () => {},
  isLingering = false,
  lingerEvent,
  dagContext,
  telemetryData,
  // Filters (Issue #445)
  filterStats,
  showFiltered = false,
  onToggleShowFiltered = () => {},
  onResetDefaults,
  className = '',
}) => {
  const refConfigRef = useRef<ReferenceConfigPanelHandle>(null);

  // Collapse state for sidebar sections
  const [isReferenceConfigCollapsed, setIsReferenceConfigCollapsed] = useState(false);
  const [isFiltersCollapsed, setIsFiltersCollapsed] = useState(false);
  const [isStatsCollapsed, setIsStatsCollapsed] = useState(false);

  return (
    <aside className={`flex flex-col bg-app-secondary border-r border-app-border h-full ${className}`}>
      {/* Reference Config Panel */}
      {referenceConfig && onReferenceConfigUpdate && (
        <div className="border-b border-app-border">
          <div className="flex items-center">
            <button
              className="flex-1 p-4 hover:bg-app-card/30 transition-colors text-left"
              onClick={() => setIsReferenceConfigCollapsed(!isReferenceConfigCollapsed)}
            >
              <h3 className="text-xs font-bold text-app-muted uppercase tracking-wider flex items-center gap-2">
                {isReferenceConfigCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                <Settings size={14} />
                Reference Config
              </h3>
            </button>
            <button
              onClick={() => refConfigRef.current?.reset()}
              className="p-4 text-app-muted hover:text-white transition-colors"
              title="Reset to defaults"
            >
              <RotateCcw size={14} />
            </button>
          </div>
          {!isReferenceConfigCollapsed && (
            <div className="px-4 pb-4">
              <ReferenceConfigPanel
                ref={refConfigRef}
                config={referenceConfig}
                onConfigUpdate={onReferenceConfigUpdate}
                hideHeader={true}
              />
            </div>
          )}
        </div>
      )}

      {/* Feedback Section */}
      {showFeedback && feedbackContext && currentPlaybackBar !== undefined && (
        <FeedbackForm
          isLingering={isLingering}
          lingerEvent={lingerEvent}
          currentPlaybackBar={currentPlaybackBar}
          feedbackContext={feedbackContext}
          onFeedbackFocus={onFeedbackFocus}
          onFeedbackBlur={onFeedbackBlur}
          onPausePlayback={onPausePlayback}
          dagContext={dagContext}
          screenshotTargetRef={screenshotTargetRef}
          attachedItems={attachedItems}
          onDetachItem={onDetachItem}
          onClearAttachments={onClearAttachments}
        />
      )}

      {/* Filters Panel (Issue #445 - moved from bottom panel) */}
      <div className="border-t border-app-border">
        <button
          className="w-full p-4 hover:bg-app-card/30 transition-colors text-left"
          onClick={() => setIsFiltersCollapsed(!isFiltersCollapsed)}
        >
          <h3 className="text-xs font-bold text-app-muted uppercase tracking-wider flex items-center gap-2">
            {isFiltersCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
            <Filter size={14} />
            Filters
          </h3>
        </button>
        {!isFiltersCollapsed && (
          <div className="px-4 pb-4">
            <FiltersPanel
              filterStats={filterStats ?? null}
              showFiltered={showFiltered}
              onToggleShowFiltered={onToggleShowFiltered}
            />
          </div>
        )}
      </div>

      {/* Reference Stats */}
      <div className="border-t border-app-border">
        <button
          className="w-full p-4 hover:bg-app-card/30 transition-colors text-left"
          onClick={() => setIsStatsCollapsed(!isStatsCollapsed)}
        >
          <h3 className="text-xs font-bold text-app-muted uppercase tracking-wider flex items-center gap-2">
            {isStatsCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
            <Activity size={14} />
            Reference Stats
          </h3>
        </button>
        {!isStatsCollapsed && (
          <div className="px-4 pb-4">
            <ReferenceStatsPanel telemetryData={telemetryData || null} />
          </div>
        )}
      </div>

      {/* Bottom Actions */}
      {onResetDefaults && (
        <div className="mt-auto p-4 border-t border-app-border bg-app-bg/30">
          <button
            onClick={onResetDefaults}
            className="w-full text-xs text-app-muted hover:text-white text-center py-2 border border-dashed border-app-border rounded hover:border-app-muted transition-colors"
          >
            Reset to Defaults
          </button>
        </div>
      )}
    </aside>
  );
};
