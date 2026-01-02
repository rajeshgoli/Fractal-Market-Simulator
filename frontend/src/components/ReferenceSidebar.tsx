import React, { useState, useRef, useImperativeHandle, forwardRef, useMemo } from 'react';
import { ChevronDown, ChevronRight, Settings, RotateCcw, Layers, Activity, Loader, Info } from 'lucide-react';
import {
  ReferenceConfig,
  StructurePanelResponse,
  ReferenceSwing,
  TelemetryPanelResponse,
  DEFAULT_REFERENCE_CONFIG,
} from '../lib/api';
import { FeedbackForm } from './FeedbackForm';
import type { FeedbackContext, DagContext } from './FeedbackForm';
import { StructurePanel } from './StructurePanel';
import { ReplayEvent } from '../lib/api';
import { AttachableItem } from './DAGStatePanel';

// ============================================================================
// Reference Config Panel (Issue #424)
// ============================================================================

export interface ReferenceConfigPanelHandle {
  reset: () => void;
}

interface ReferenceConfigPanelProps {
  config: ReferenceConfig;
  onConfigUpdate: (config: ReferenceConfig) => void | Promise<void>;
  hideHeader?: boolean;
}

// Tooltip definitions for each parameter
const TOOLTIPS = {
  big_range_weight: "Rank by leg size. Larger legs score higher.",
  big_impulse_weight: "Rank by move speed. Fast, impulsive moves score higher.",
  big_recency_weight: "Rank by age. Recent legs score higher.",
  small_range_weight: "Rank by leg size. Larger legs score higher.",
  small_impulse_weight: "Rank by move speed. Fast, impulsive moves score higher.",
  small_recency_weight: "Rank by age. Recent legs score higher.",
  range_counter_weight: "Rank by structural importance: leg size \u00d7 counter-trend defense. Standalone mode \u2014 disables other components.",
  formation_fib_threshold: "Retracement required before leg forms. Higher = stricter formation (only clear reversals).",
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

  // Check if Range×Counter standalone mode is active
  const isStandaloneMode = localConfig.range_counter_weight > 0;

  // Track if config has changes from server config
  const hasChanges = useMemo(() => {
    return (
      localConfig.big_range_weight !== config.big_range_weight ||
      localConfig.big_impulse_weight !== config.big_impulse_weight ||
      localConfig.big_recency_weight !== config.big_recency_weight ||
      localConfig.small_range_weight !== config.small_range_weight ||
      localConfig.small_impulse_weight !== config.small_impulse_weight ||
      localConfig.small_recency_weight !== config.small_recency_weight ||
      localConfig.range_counter_weight !== config.range_counter_weight ||
      localConfig.formation_fib_threshold !== config.formation_fib_threshold
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

  return (
    <div className="space-y-4">
      {!hideHeader && (
        <div className="flex items-center gap-2 mb-2">
          <Settings size={14} className="text-trading-blue" />
          <h3 className="text-xs font-semibold text-app-text uppercase tracking-wider">Reference Config</h3>
        </div>
      )}

      {/* Range×Counter Standalone Mode */}
      <div className="space-y-2">
        <div className="text-[10px] font-medium text-app-muted uppercase tracking-wider">Standalone Mode</div>
        <SliderRow
          label="Range×Counter"
          value={localConfig.range_counter_weight}
          onChange={(v) => handleSliderChange('range_counter_weight', v)}
          min={0}
          max={1}
          step={0.1}
          disabled={isUpdating}
          tooltip={TOOLTIPS.range_counter_weight}
          showTooltip={showTooltip === 'range_counter_weight'}
          onToggleTooltip={() => toggleTooltip('range_counter_weight')}
        />
        {isStandaloneMode && (
          <div className="text-[9px] text-yellow-500 bg-yellow-500/10 px-2 py-1 rounded">
            Standalone mode active. Other weight sliders disabled.
          </div>
        )}
      </div>

      {/* Base Weights (L/XL) */}
      <div className={`space-y-2 ${isStandaloneMode ? 'opacity-50' : ''}`}>
        <div className="text-[10px] font-medium text-app-muted uppercase tracking-wider">Base Weights (L/XL)</div>
        <SliderRow
          label="Range"
          value={localConfig.big_range_weight}
          onChange={(v) => handleSliderChange('big_range_weight', v)}
          min={0}
          max={1}
          step={0.1}
          disabled={isUpdating || isStandaloneMode}
          tooltip={TOOLTIPS.big_range_weight}
          showTooltip={showTooltip === 'big_range_weight'}
          onToggleTooltip={() => toggleTooltip('big_range_weight')}
        />
        <SliderRow
          label="Impulse"
          value={localConfig.big_impulse_weight}
          onChange={(v) => handleSliderChange('big_impulse_weight', v)}
          min={0}
          max={1}
          step={0.1}
          disabled={isUpdating || isStandaloneMode}
          tooltip={TOOLTIPS.big_impulse_weight}
          showTooltip={showTooltip === 'big_impulse_weight'}
          onToggleTooltip={() => toggleTooltip('big_impulse_weight')}
        />
        <SliderRow
          label="Recency"
          value={localConfig.big_recency_weight}
          onChange={(v) => handleSliderChange('big_recency_weight', v)}
          min={0}
          max={1}
          step={0.1}
          disabled={isUpdating || isStandaloneMode}
          tooltip={TOOLTIPS.big_recency_weight}
          showTooltip={showTooltip === 'big_recency_weight'}
          onToggleTooltip={() => toggleTooltip('big_recency_weight')}
        />
      </div>

      {/* Base Weights (S/M) */}
      <div className={`space-y-2 ${isStandaloneMode ? 'opacity-50' : ''}`}>
        <div className="text-[10px] font-medium text-app-muted uppercase tracking-wider">Base Weights (S/M)</div>
        <SliderRow
          label="Range"
          value={localConfig.small_range_weight}
          onChange={(v) => handleSliderChange('small_range_weight', v)}
          min={0}
          max={1}
          step={0.1}
          disabled={isUpdating || isStandaloneMode}
          tooltip={TOOLTIPS.small_range_weight}
          showTooltip={showTooltip === 'small_range_weight'}
          onToggleTooltip={() => toggleTooltip('small_range_weight')}
        />
        <SliderRow
          label="Impulse"
          value={localConfig.small_impulse_weight}
          onChange={(v) => handleSliderChange('small_impulse_weight', v)}
          min={0}
          max={1}
          step={0.1}
          disabled={isUpdating || isStandaloneMode}
          tooltip={TOOLTIPS.small_impulse_weight}
          showTooltip={showTooltip === 'small_impulse_weight'}
          onToggleTooltip={() => toggleTooltip('small_impulse_weight')}
        />
        <SliderRow
          label="Recency"
          value={localConfig.small_recency_weight}
          onChange={(v) => handleSliderChange('small_recency_weight', v)}
          min={0}
          max={1}
          step={0.1}
          disabled={isUpdating || isStandaloneMode}
          tooltip={TOOLTIPS.small_recency_weight}
          showTooltip={showTooltip === 'small_recency_weight'}
          onToggleTooltip={() => toggleTooltip('small_recency_weight')}
        />
      </div>

      {/* Formation */}
      <div className="space-y-2">
        <div className="text-[10px] font-medium text-app-muted uppercase tracking-wider">Formation</div>
        <SliderRow
          label="Threshold"
          value={localConfig.formation_fib_threshold}
          onChange={(v) => handleSliderChange('formation_fib_threshold', v)}
          min={0.2}
          max={0.5}
          step={0.01}
          formatValue={(v) => v.toFixed(3)}
          disabled={isUpdating}
          tooltip={TOOLTIPS.formation_fib_threshold}
          showTooltip={showTooltip === 'formation_fib_threshold'}
          onToggleTooltip={() => toggleTooltip('formation_fib_threshold')}
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

// Slider row component with tooltip support
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
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1 w-24">
          <span className={`text-[10px] ${disabled ? 'text-app-muted/50' : 'text-app-muted'}`}>{label}</span>
          {tooltip && onToggleTooltip && (
            <button
              onClick={onToggleTooltip}
              className="text-app-muted hover:text-app-text transition-colors"
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
        <span className={`text-[10px] font-mono w-10 text-right ${disabled ? 'text-app-muted/50' : 'text-app-text'}`}>
          {formatValue(value)}
        </span>
      </div>
      {showTooltip && tooltip && (
        <p className="text-[9px] text-app-muted bg-app-bg/50 p-1.5 rounded ml-0">
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

  const { counts_by_scale, total_count, bull_count, bear_count, direction_imbalance, imbalance_ratio } = telemetryData;

  return (
    <div className="space-y-3">
      {/* Counts by Scale */}
      <div className="grid grid-cols-4 gap-1">
        {['XL', 'L', 'M', 'S'].map((scale) => {
          const count = counts_by_scale[scale] || 0;
          const scaleColor = getScaleBadgeColor(scale);
          return (
            <div key={scale} className="text-center">
              <span className={`text-[9px] font-medium px-1.5 py-0.5 rounded ${scaleColor.bg} ${scaleColor.text}`}>
                {scale}
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

function getScaleBadgeColor(scale: string): { bg: string; text: string } {
  switch (scale) {
    case 'XL': return { bg: 'bg-purple-600/20', text: 'text-purple-400' };
    case 'L': return { bg: 'bg-blue-600/20', text: 'text-blue-400' };
    case 'M': return { bg: 'bg-green-600/20', text: 'text-green-400' };
    case 'S': return { bg: 'bg-gray-600/20', text: 'text-gray-400' };
    default: return { bg: 'bg-gray-600/20', text: 'text-gray-400' };
  }
}

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

  // Structure Panel
  structureData?: StructurePanelResponse;
  references?: ReferenceSwing[];
  trackedLegIds?: Set<string>;
  onToggleTrack?: (legId: string) => Promise<{ success: boolean; error?: string }>;

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
  structureData,
  references = [],
  trackedLegIds = new Set(),
  onToggleTrack = async () => ({ success: true }),
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

      {/* Structure Panel */}
      <div className="border-t border-app-border">
        <button
          className="w-full p-4 hover:bg-app-card/30 transition-colors text-left"
          onClick={() => setIsStructureCollapsed(!isStructureCollapsed)}
        >
          <h3 className="text-xs font-bold text-app-muted uppercase tracking-wider flex items-center gap-2">
            {isStructureCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
            <Layers size={14} />
            Structure
          </h3>
        </button>
        {!isStructureCollapsed && (
          <div className="px-4 pb-4">
            <StructurePanel
              structureData={structureData || null}
              references={references}
              trackedLegIds={trackedLegIds}
              onToggleTrack={onToggleTrack}
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
