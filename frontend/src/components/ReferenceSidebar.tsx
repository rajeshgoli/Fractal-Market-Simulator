import React, { useState, useRef, useImperativeHandle, forwardRef, useMemo } from 'react';
import { ChevronDown, ChevronRight, Settings, RotateCcw, Activity, Loader, Info } from 'lucide-react';
import {
  ReferenceConfig,
  ReferenceSwing,
  TelemetryPanelResponse,
  DEFAULT_REFERENCE_CONFIG,
} from '../lib/api';
import { FeedbackForm } from './FeedbackForm';
import type { FeedbackContext, DagContext } from './FeedbackForm';
import { LevelsAtPlayPanel } from './LevelsAtPlayPanel';
import { ReplayEvent } from '../lib/api';
import { AttachableItem } from './DAGStatePanel';
import { getBinBadgeColor } from '../utils/binUtils';

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
const FORMATION_FIB_LABELS = ['Off', '.236', '.382', '.5', '.618'];

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
  origin_breach_tolerance: "How far price can breach origin before leg is invalidated. Higher = more tolerant.",
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
  const [showTooltip, setShowTooltip] = useState<string | null>(null);
  const hasAppliedRef = React.useRef(false);

  // Track if config has changes from server config (#436, #442, #444: unified weights)
  const hasChanges = useMemo(() => {
    return (
      localConfig.range_weight !== config.range_weight ||
      localConfig.impulse_weight !== config.impulse_weight ||
      localConfig.recency_weight !== config.recency_weight ||
      localConfig.depth_weight !== config.depth_weight ||
      localConfig.counter_weight !== config.counter_weight ||
      localConfig.range_counter_weight !== config.range_counter_weight ||
      localConfig.formation_fib_threshold !== config.formation_fib_threshold ||
      localConfig.origin_breach_tolerance !== config.origin_breach_tolerance ||
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

  const toggleTooltip = (key: string) => {
    setShowTooltip(showTooltip === key ? null : key);
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

    return (
      <div className="space-y-0.5">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 w-[55px] flex-shrink-0">
            <span className="text-[10px] text-app-muted whitespace-nowrap">Threshold</span>
            <button
              onClick={() => toggleTooltip('formation_fib_threshold')}
              className="text-app-muted hover:text-app-text transition-colors flex-shrink-0"
              title={TOOLTIPS.formation_fib_threshold}
            >
              <Info size={10} />
            </button>
          </div>
          <input
            type="range"
            min={0}
            max={FORMATION_FIB_VALUES.length - 1}
            step={1}
            value={sliderIndex}
            onChange={(e) => handleSliderChange('formation_fib_threshold', FORMATION_FIB_VALUES[parseInt(e.target.value)])}
            className="flex-1 h-1 bg-app-border rounded-lg appearance-none cursor-pointer accent-trading-blue"
            disabled={isUpdating}
          />
          <span className="text-[10px] font-mono w-[50px] text-right text-app-text flex-shrink-0">
            {displayValue}
          </span>
        </div>
        {/* Endpoint labels only - full labels don't fit in narrow sidebar */}
        <div className="flex items-center gap-2 text-[8px] text-app-muted">
          <div className="w-[55px] flex-shrink-0"></div>
          <span>Off</span>
          <span className="flex-1"></span>
          <span>.618</span>
          <div className="w-[50px] flex-shrink-0"></div>
        </div>
        {showTooltip === 'formation_fib_threshold' && (
          <p className="text-[9px] text-app-muted bg-app-bg/50 p-1.5 rounded">
            {TOOLTIPS.formation_fib_threshold}
          </p>
        )}
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

      {/* ORIGIN BREACH Section (#444) - continuous slider 0-0.3 */}
      <div className="space-y-2">
        <div className="text-[10px] font-medium text-app-muted uppercase tracking-wider">Origin Breach</div>
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 w-[55px] flex-shrink-0">
              <span className="text-[10px] text-app-muted whitespace-nowrap">Tolerance</span>
              <button
                onClick={() => toggleTooltip('origin_breach_tolerance')}
                className="text-app-muted hover:text-app-text transition-colors flex-shrink-0"
                title={TOOLTIPS.origin_breach_tolerance}
              >
                <Info size={10} />
              </button>
            </div>
            <input
              type="range"
              min={0}
              max={0.3}
              step={0.01}
              value={localConfig.origin_breach_tolerance ?? 0}
              onChange={(e) => handleSliderChange('origin_breach_tolerance', parseFloat(e.target.value))}
              className="flex-1 h-1 bg-app-border rounded-lg appearance-none cursor-pointer"
              style={{ accentColor: getBreachColor(localConfig.origin_breach_tolerance ?? 0, 0.3) }}
              disabled={isUpdating}
            />
            <span className="text-[10px] font-mono w-[50px] text-right text-app-text flex-shrink-0">
              {(localConfig.origin_breach_tolerance ?? 0).toFixed(2)}
            </span>
          </div>
          {showTooltip === 'origin_breach_tolerance' && (
            <p className="text-[9px] text-app-muted bg-app-bg/50 p-1.5 rounded">
              {TOOLTIPS.origin_breach_tolerance}
            </p>
          )}
        </div>
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
          showTooltip={showTooltip === 'range_weight'}
          onToggleTooltip={() => toggleTooltip('range_weight')}
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
          showTooltip={showTooltip === 'counter_weight'}
          onToggleTooltip={() => toggleTooltip('counter_weight')}
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
          showTooltip={showTooltip === 'range_counter_weight'}
          onToggleTooltip={() => toggleTooltip('range_counter_weight')}
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
          showTooltip={showTooltip === 'impulse_weight'}
          onToggleTooltip={() => toggleTooltip('impulse_weight')}
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
          showTooltip={showTooltip === 'depth_weight'}
          onToggleTooltip={() => toggleTooltip('depth_weight')}
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
          showTooltip={showTooltip === 'recency_weight'}
          onToggleTooltip={() => toggleTooltip('recency_weight')}
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
          showTooltip={showTooltip === 'top_n'}
          onToggleTooltip={() => toggleTooltip('top_n')}
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

// Slider row component with tooltip support (#444: uniform widths)
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
  showTooltip?: boolean;
  onToggleTooltip?: () => void;
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
  showTooltip = false,
  onToggleTooltip,
}) => {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1 w-[55px] flex-shrink-0">
          <span className={`text-[10px] whitespace-nowrap ${disabled ? 'text-app-muted/50' : 'text-app-muted'}`}>{label}</span>
          {tooltip && onToggleTooltip && (
            <button
              onClick={onToggleTooltip}
              className="text-app-muted hover:text-app-text transition-colors flex-shrink-0"
              title={tooltip}
            >
              <Info size={10} />
            </button>
          )}
        </div>
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          className={`flex-1 h-1 bg-app-border rounded-lg appearance-none ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'} accent-trading-blue`}
          disabled={disabled}
        />
        <span className={`text-[10px] font-mono w-[50px] text-right flex-shrink-0 ${disabled ? 'text-app-muted/50' : 'text-app-text'}`}>
          {formatValue(value)}
        </span>
      </div>
      {showTooltip && tooltip && (
        <p className="text-[9px] text-app-muted bg-app-bg/50 p-1.5 rounded">
          {tooltip}
        </p>
      )}
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
// Reference Sidebar (Issue #424)
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

  // Levels at Play Panel (Issue #430)
  references?: ReferenceSwing[];
  totalReferenceCount?: number;
  selectedLegId?: string | null;
  hoveredLegId?: string | null;
  onHoverLeg?: (legId: string | null) => void;
  onSelectLeg?: (legId: string) => void;
  // Pagination
  currentPage?: number;
  pageSize?: number;
  onPrevPage?: () => void;
  onNextPage?: () => void;

  // Telemetry (Reference Stats)
  telemetryData?: TelemetryPanelResponse;

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
  // Levels at Play Panel (Issue #430)
  references = [],
  totalReferenceCount = 0,
  selectedLegId = null,
  hoveredLegId = null,
  onHoverLeg = () => {},
  onSelectLeg = () => {},
  // Pagination
  currentPage = 0,
  pageSize = 5,
  onPrevPage = () => {},
  onNextPage = () => {},
  telemetryData,
  onResetDefaults,
  className = '',
}) => {
  const refConfigRef = useRef<ReferenceConfigPanelHandle>(null);

  // Collapse state for sidebar sections
  const [isReferenceConfigCollapsed, setIsReferenceConfigCollapsed] = useState(false);
  const [isStructureCollapsed, setIsStructureCollapsed] = useState(false);
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

      {/* Levels at Play Panel (Issue #430) */}
      <div className="border-t border-app-border">
        <button
          className="w-full p-4 hover:bg-app-card/30 transition-colors text-left"
          onClick={() => setIsStructureCollapsed(!isStructureCollapsed)}
        >
          <h3 className="text-xs font-bold text-app-muted uppercase tracking-wider flex items-center gap-2">
            {isStructureCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
            Levels at Play
          </h3>
        </button>
        {!isStructureCollapsed && (
          <div className="px-4 pb-4">
            <LevelsAtPlayPanel
              references={references}
              totalReferenceCount={totalReferenceCount}
              selectedLegId={selectedLegId}
              hoveredLegId={hoveredLegId}
              onHoverLeg={onHoverLeg}
              onSelectLeg={onSelectLeg}
              currentPage={currentPage}
              pageSize={pageSize}
              onPrevPage={onPrevPage}
              onNextPage={onNextPage}
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
