import React, { useState, useCallback, forwardRef, useImperativeHandle, useMemo } from 'react';
import { Settings, RotateCcw, Loader } from 'lucide-react';
import { DetectionConfig, DEFAULT_DETECTION_CONFIG } from '../types';
import { updateDetectionConfig, DetectionConfigUpdateRequest } from '../lib/api';

interface SliderConfig {
  key: string;
  label: string;
  min: number;
  max: number;
  step: number;
  description: string;
  displayAsPercent?: boolean;  // Display value as percentage (multiply by 100, add %)
  colorMode?: 'restrictive-right' | 'restrictive-left';  // Which direction is more restrictive
}

// Slider configurations for global parameters (excluding turn ratio which has special handling)
const GLOBAL_SLIDERS: SliderConfig[] = [
  { key: 'stale_extension_threshold', label: 'Stale Extension', min: 1.0, max: 5.0, step: 0.1, description: 'Extension multiple for stale pruning', colorMode: 'restrictive-left' },
  { key: 'origin_range_threshold', label: 'Origin Range %', min: 0.0, max: 0.10, step: 0.01, description: 'Range similarity threshold for origin-proximity pruning', displayAsPercent: true, colorMode: 'restrictive-right' },
  { key: 'origin_time_threshold', label: 'Origin Time %', min: 0.0, max: 0.10, step: 0.01, description: 'Time proximity threshold for origin-proximity pruning', displayAsPercent: true, colorMode: 'restrictive-right' },
  { key: 'min_branch_ratio', label: 'Branch Ratio', min: 0.0, max: 0.20, step: 0.01, description: 'Min ratio of child counter-trend to parent counter-trend for origin domination', displayAsPercent: true, colorMode: 'restrictive-right' },
];

// Turn ratio mode options (#342)
type TurnRatioMode = 'disabled' | 'threshold' | 'topk';

// Toggle configurations for pruning algorithms
interface ToggleConfig {
  key: keyof DetectionConfig;
  label: string;
  description: string;
}

const PRUNE_TOGGLES: ToggleConfig[] = [
  { key: 'enable_engulfed_prune', label: 'Engulfed', description: 'Delete legs breached on both origin and pivot sides' },
  { key: 'enable_inner_structure_prune', label: 'Inner Structure', description: 'Prune legs with same pivot as parent' },
];

// Fibonacci level options for Formation and Invalidation thresholds
const FIB_LEVEL_OPTIONS = [
  { value: 0.10, label: '10%' },
  { value: 0.236, label: '23.6%' },
  { value: 0.382, label: '38.2%' },
  { value: 0.50, label: '50%' },
  { value: 0.618, label: '61.8%' },
  { value: 0.764, label: '76.4%' },
  { value: 0.90, label: '90%' },
  { value: 1.00, label: '100%' },
];

interface DetectionConfigPanelProps {
  config: DetectionConfig;
  onConfigUpdate: (config: DetectionConfig) => void;
  isCalibrated: boolean;
  className?: string;
  hideHeader?: boolean;  // Hide header when parent provides collapsible container (#310)
  initialLocalConfig?: DetectionConfig;  // Seeds local state from saved preferences (UI only, not applied to BE)
}

// Expose reset method via ref for external triggering
export interface DetectionConfigPanelHandle {
  reset: () => void;
}

export const DetectionConfigPanel = forwardRef<DetectionConfigPanelHandle, DetectionConfigPanelProps>(({
  config,
  onConfigUpdate,
  isCalibrated,
  className = '',
  hideHeader = false,
  initialLocalConfig,
}, ref) => {
  const [isUpdating, setIsUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Initialize local state from saved preferences if available, otherwise from server config
  const [localConfig, setLocalConfig] = useState<DetectionConfig>(
    initialLocalConfig ?? config
  );

  // Track whether we've already applied once (to know when to sync after Apply)
  const hasAppliedRef = React.useRef(false);

  // Sync local config when config prop changes ONLY after an Apply operation
  // On initial mount with saved preferences, we want to show those, not server config
  React.useEffect(() => {
    if (hasAppliedRef.current) {
      setLocalConfig(config);
      hasAppliedRef.current = false;
    }
  }, [config]);

  // Compute hasChanges by comparing FE state (localConfig) with BE state (config prop)
  const hasChanges = useMemo(() => {
    return (
      localConfig.bull.formation_fib !== config.bull.formation_fib ||
      localConfig.bull.invalidation_threshold !== config.bull.invalidation_threshold ||
      localConfig.bear.formation_fib !== config.bear.formation_fib ||
      localConfig.bear.invalidation_threshold !== config.bear.invalidation_threshold ||
      localConfig.stale_extension_threshold !== config.stale_extension_threshold ||
      localConfig.origin_range_threshold !== config.origin_range_threshold ||
      localConfig.origin_time_threshold !== config.origin_time_threshold ||
      localConfig.min_branch_ratio !== config.min_branch_ratio ||
      localConfig.min_turn_ratio !== config.min_turn_ratio ||
      localConfig.max_turns_per_pivot !== config.max_turns_per_pivot ||
      localConfig.enable_engulfed_prune !== config.enable_engulfed_prune ||
      localConfig.enable_inner_structure_prune !== config.enable_inner_structure_prune
    );
  }, [localConfig, config]);

  // Determine current turn ratio mode based on config values (#342)
  const turnRatioMode: TurnRatioMode = useMemo(() => {
    if (localConfig.min_turn_ratio > 0) return 'threshold';
    if (localConfig.max_turns_per_pivot > 0) return 'topk';
    return 'disabled';
  }, [localConfig.min_turn_ratio, localConfig.max_turns_per_pivot]);

  // Handle turn ratio mode change (#342)
  const handleTurnRatioModeChange = useCallback((mode: TurnRatioMode) => {
    setLocalConfig(prev => {
      if (mode === 'disabled') {
        return { ...prev, min_turn_ratio: 0, max_turns_per_pivot: 0 };
      } else if (mode === 'threshold') {
        // Switch to threshold mode: set default threshold, clear top-k
        return { ...prev, min_turn_ratio: 0.10, max_turns_per_pivot: 0 };
      } else {
        // Switch to top-k mode: set default k, clear threshold
        return { ...prev, min_turn_ratio: 0, max_turns_per_pivot: 3 };
      }
    });
    setError(null);
  }, []);

  const handleSliderChange = useCallback((
    direction: 'bull' | 'bear' | 'global',
    key: string,
    value: number
  ) => {
    setLocalConfig(prev => {
      if (direction === 'global') {
        return { ...prev, [key]: value };
      }
      return {
        ...prev,
        [direction]: { ...prev[direction], [key]: value },
      };
    });
    setError(null);
  }, []);

  const handleToggleChange = useCallback((key: keyof DetectionConfig, value: boolean) => {
    setLocalConfig(prev => ({ ...prev, [key]: value }));
    setError(null);
  }, []);

  const handleApply = useCallback(async () => {
    if (!isCalibrated) {
      setError('Must calibrate before updating config');
      return;
    }

    setIsUpdating(true);
    setError(null);

    try {
      // Build request with all current values
      const request: DetectionConfigUpdateRequest = {
        bull: {
          formation_fib: localConfig.bull.formation_fib,
          invalidation_threshold: localConfig.bull.invalidation_threshold,
        },
        bear: {
          formation_fib: localConfig.bear.formation_fib,
          invalidation_threshold: localConfig.bear.invalidation_threshold,
        },
        stale_extension_threshold: localConfig.stale_extension_threshold,
        origin_range_threshold: localConfig.origin_range_threshold,
        origin_time_threshold: localConfig.origin_time_threshold,
        min_branch_ratio: localConfig.min_branch_ratio,
        min_turn_ratio: localConfig.min_turn_ratio,
        max_turns_per_pivot: localConfig.max_turns_per_pivot,
        // Pruning algorithm toggles
        enable_engulfed_prune: localConfig.enable_engulfed_prune,
        enable_inner_structure_prune: localConfig.enable_inner_structure_prune,
      };

      const updatedConfig = await updateDetectionConfig(request);
      hasAppliedRef.current = true;  // Signal that next config change should sync localConfig
      onConfigUpdate(updatedConfig);
      // hasChanges auto-computes to false when config prop updates
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update config');
    } finally {
      setIsUpdating(false);
    }
  }, [localConfig, isCalibrated, onConfigUpdate]);

  const handleReset = useCallback(() => {
    setLocalConfig(DEFAULT_DETECTION_CONFIG);
    setError(null);
    // hasChanges auto-computes based on localConfig vs config (BE state)
  }, []);

  // Expose reset method via ref for external triggering (e.g., from Sidebar header)
  useImperativeHandle(ref, () => ({
    reset: handleReset,
  }), [handleReset]);

  const renderSlider = (
    direction: 'bull' | 'bear' | 'global',
    slider: SliderConfig
  ) => {
    const defaultValue = direction === 'global'
      ? (DEFAULT_DETECTION_CONFIG[slider.key as keyof DetectionConfig] as number)
      : DEFAULT_DETECTION_CONFIG[direction][slider.key as keyof typeof DEFAULT_DETECTION_CONFIG.bull];

    // Get value with fallback to default if undefined (handles missing fields from older backends)
    const rawValue = direction === 'global'
      ? (localConfig[slider.key as keyof DetectionConfig] as number)
      : localConfig[direction][slider.key as keyof typeof localConfig.bull];
    const value = rawValue ?? defaultValue;

    const isDefault = Math.abs(value - defaultValue) < 0.001;

    // Format display value (as percentage if configured, or integer for step >= 1)
    const displayValue = slider.displayAsPercent
      ? `${Math.round(value * 100)}%`
      : slider.step >= 1 ? String(Math.round(value)) : value.toFixed(slider.step >= 0.1 ? 1 : 2);

    // Calculate position ratio for color gradient (0 = min, 1 = max)
    const positionRatio = (value - slider.min) / (slider.max - slider.min);

    // Calculate color based on position and restrictiveness mode
    // restrictive-right: left=green, right=red (higher values are more restrictive)
    // restrictive-left: left=red, right=green (lower values are more restrictive)
    const getSliderColor = () => {
      if (!slider.colorMode) return 'rgb(59, 130, 246)'; // default blue

      const ratio = slider.colorMode === 'restrictive-right' ? positionRatio : 1 - positionRatio;
      // Interpolate from green (relaxed) to red (restrictive)
      const r = Math.round(34 + ratio * (239 - 34));  // 34 (green) -> 239 (red)
      const g = Math.round(197 - ratio * (197 - 68)); // 197 (green) -> 68 (red)
      const b = Math.round(94 - ratio * (94 - 68));   // 94 (green) -> 68 (red)
      return `rgb(${r}, ${g}, ${b})`;
    };

    const sliderColor = getSliderColor();

    return (
      <div key={`${direction}-${slider.key}`} className="space-y-1">
        <div className="flex items-center justify-between">
          <span className="text-xs text-app-muted" title={slider.description}>
            {slider.label}
          </span>
          <span
            className={`text-xs font-mono ${isDefault ? 'text-app-muted' : ''}`}
            style={!isDefault ? { color: sliderColor } : undefined}
          >
            {displayValue}
          </span>
        </div>
        <input
          type="range"
          min={slider.min}
          max={slider.max}
          step={slider.step}
          value={value}
          onChange={(e) => handleSliderChange(direction, slider.key, parseFloat(e.target.value))}
          className="w-full h-1.5 bg-app-border rounded-lg appearance-none cursor-pointer"
          style={{ accentColor: sliderColor }}
          disabled={isUpdating}
        />
      </div>
    );
  };

  const renderToggle = (toggle: ToggleConfig) => {
    const value = localConfig[toggle.key] as boolean;
    const defaultValue = DEFAULT_DETECTION_CONFIG[toggle.key] as boolean;
    const isDefault = value === defaultValue;

    return (
      <label
        key={toggle.key}
        className="flex items-center justify-between cursor-pointer group"
        title={toggle.description}
      >
        <span className={`text-xs ${isDefault ? 'text-app-muted' : 'text-trading-blue'}`}>
          {toggle.label}
        </span>
        <div className="relative">
          <input
            type="checkbox"
            checked={value}
            onChange={(e) => handleToggleChange(toggle.key, e.target.checked)}
            disabled={isUpdating}
            className="sr-only peer"
          />
          <div className={`w-8 h-4 rounded-full transition-colors ${
            value ? 'bg-trading-blue' : 'bg-app-border'
          } peer-disabled:opacity-50`} />
          <div className={`absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white transition-transform ${
            value ? 'translate-x-4' : 'translate-x-0'
          }`} />
        </div>
      </label>
    );
  };

  const renderFibSelect = (
    direction: 'bull' | 'bear',
    key: 'formation_fib' | 'invalidation_threshold'
  ) => {
    const value = localConfig[direction][key];
    const colorClass = direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear';
    const borderClass = direction === 'bull' ? 'focus:border-trading-bull' : 'focus:border-trading-bear';

    return (
      <select
        value={value}
        onChange={(e) => handleSliderChange(direction, key, parseFloat(e.target.value))}
        className={`w-16 px-1 py-0.5 text-center text-xs font-mono bg-app-bg border border-app-border rounded ${colorClass} ${borderClass} focus:outline-none cursor-pointer`}
        disabled={isUpdating}
      >
        {FIB_LEVEL_OPTIONS.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
    );
  };

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Header - hidden when parent provides collapsible container (#310) */}
      {!hideHeader && (
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold text-app-muted uppercase tracking-wider flex items-center gap-2">
            <Settings size={14} />
            Detection Config
          </h3>
          <button
            onClick={handleReset}
            className="text-xs text-app-muted hover:text-white transition-colors"
            title="Reset to defaults"
            disabled={isUpdating}
          >
            <RotateCcw size={14} />
          </button>
        </div>
      )}

      {/* Global Thresholds */}
      <div className="space-y-2">
        <span className="text-xs font-medium text-app-text">Global</span>
        <div className="pl-4 space-y-3">
          {GLOBAL_SLIDERS.map(slider => renderSlider('global', slider))}
        </div>
      </div>

      {/* Turn Ratio Mode (#342) */}
      <div className="space-y-2">
        <span className="text-xs font-medium text-app-text">Turn Ratio Pruning</span>
        <div className="pl-4 space-y-2">
          {/* Mode selector */}
          <div className="flex gap-1">
            {(['disabled', 'threshold', 'topk'] as TurnRatioMode[]).map(mode => (
              <button
                key={mode}
                onClick={() => handleTurnRatioModeChange(mode)}
                disabled={isUpdating}
                className={`px-2 py-1 text-xs rounded transition-colors ${
                  turnRatioMode === mode
                    ? 'bg-trading-blue text-white'
                    : 'bg-app-border text-app-muted hover:text-white'
                }`}
              >
                {mode === 'disabled' ? 'Off' : mode === 'threshold' ? '%' : 'Top-k'}
              </button>
            ))}
          </div>

          {/* Threshold slider (visible when threshold mode) */}
          {turnRatioMode === 'threshold' && (
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-xs text-app-muted" title="Min turn ratio for sibling pruning (counter-leg range / leg range)">
                  Turn Ratio %
                </span>
                <span className="text-xs font-mono text-trading-blue">
                  {Math.round((localConfig.min_turn_ratio ?? 0) * 100)}%
                </span>
              </div>
              <input
                type="range"
                min={0.01}
                max={0.50}
                step={0.01}
                value={localConfig.min_turn_ratio ?? 0.10}
                onChange={(e) => handleSliderChange('global', 'min_turn_ratio', parseFloat(e.target.value))}
                className="w-full h-1.5 bg-app-border rounded-lg appearance-none cursor-pointer"
                style={{ accentColor: 'rgb(59, 130, 246)' }}
                disabled={isUpdating}
              />
            </div>
          )}

          {/* Top-k slider (visible when top-k mode) */}
          {turnRatioMode === 'topk' && (
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-xs text-app-muted" title="Keep only top k legs per pivot by turn ratio">
                  Max Turns
                </span>
                <span className="text-xs font-mono text-trading-blue">
                  {localConfig.max_turns_per_pivot ?? 3}
                </span>
              </div>
              <input
                type="range"
                min={1}
                max={10}
                step={1}
                value={localConfig.max_turns_per_pivot ?? 3}
                onChange={(e) => handleSliderChange('global', 'max_turns_per_pivot', parseInt(e.target.value))}
                className="w-full h-1.5 bg-app-border rounded-lg appearance-none cursor-pointer"
                style={{ accentColor: 'rgb(59, 130, 246)' }}
                disabled={isUpdating}
              />
            </div>
          )}
        </div>
      </div>

      {/* Pruning Algorithms */}
      <div className="space-y-2">
        <span className="text-xs font-medium text-app-text">Pruning Algorithms</span>
        <div className="pl-4 space-y-2">
          {PRUNE_TOGGLES.map(toggle => renderToggle(toggle))}
        </div>
      </div>

      {/* Thresholds - Compact 2x2 Grid for Formation/Invalidation */}
      <div className="space-y-2">
        <span className="text-xs font-medium text-app-text">Thresholds</span>
        {/* Header row with direction labels */}
        <div className="grid grid-cols-[1fr_auto_auto] gap-2 items-center text-xs pl-4">
          <span></span>
          <span className="flex items-center gap-1 justify-center w-16">
            <span className="w-1.5 h-1.5 rounded-full bg-trading-bull" />
            <span className="text-app-muted">Bull</span>
          </span>
          <span className="flex items-center gap-1 justify-center w-16">
            <span className="w-1.5 h-1.5 rounded-full bg-trading-bear" />
            <span className="text-app-muted">Bear</span>
          </span>
        </div>
        {/* Formation row */}
        <div className="grid grid-cols-[1fr_auto_auto] gap-2 items-center text-xs pl-4">
          <span className="text-app-muted" title="Retracement required to form leg">Formation</span>
          {renderFibSelect('bull', 'formation_fib')}
          {renderFibSelect('bear', 'formation_fib')}
        </div>
        {/* Invalidation row */}
        <div className="grid grid-cols-[1fr_auto_auto] gap-2 items-center text-xs pl-4">
          <span className="text-app-muted" title="Breach threshold for invalidation">Invalidation</span>
          {renderFibSelect('bull', 'invalidation_threshold')}
          {renderFibSelect('bear', 'invalidation_threshold')}
        </div>
      </div>

      {/* Apply Button */}
      <button
        onClick={handleApply}
        disabled={!hasChanges || isUpdating || !isCalibrated}
        className={`w-full py-2 text-xs font-medium rounded transition-colors flex items-center justify-center gap-2 ${
          hasChanges && isCalibrated && !isUpdating
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

      {/* Status/Error Message */}
      {error && (
        <p className="text-xs text-trading-bear">{error}</p>
      )}
      {!isCalibrated && (
        <p className="text-xs text-app-muted">Calibrate first to enable config changes</p>
      )}
    </div>
  );
});
