import React, { useState, useCallback, forwardRef, useImperativeHandle, useMemo } from 'react';
import { Settings, RotateCcw, Loader, Info } from 'lucide-react';
import { DetectionConfig, DEFAULT_DETECTION_CONFIG } from '../types';
import { updateDetectionConfig, DetectionConfigUpdateRequest } from '../lib/api';

interface SliderConfig {
  key: string;
  label: string;
  min: number;
  max: number;
  step: number;
  description: string;
  tooltip: string;  // Full tooltip explanation
  displayAsPercent?: boolean;  // Display value as percentage (multiply by 100, add %)
  colorMode?: 'restrictive-right' | 'restrictive-left';  // Which direction is more restrictive
}

// Prune threshold sliders (#404 - simplified config)
const PRUNE_SLIDERS: SliderConfig[] = [
  {
    key: 'stale_extension_threshold',
    label: 'Stale Extension',
    min: 1.0,
    max: 5.0,
    step: 0.1,
    description: 'Prune extended legs',
    tooltip: 'When a leg extends N times its range beyond origin, prune it. Lower = more aggressive pruning.',
    colorMode: 'restrictive-left',
  },
  {
    key: 'origin_range_threshold',
    label: 'Origin Proximity',
    min: 0.0,
    max: 0.10,
    step: 0.01,
    description: 'Consolidate similar origins',
    tooltip: 'Legs with origins within this range % are consolidated. 0 = disabled. Higher = more aggressive.',
    displayAsPercent: true,
    colorMode: 'restrictive-right',
  },
  {
    key: 'max_turns',
    label: 'Turn Ranking',
    min: 0,
    max: 20,
    step: 1,
    description: 'Max legs per pivot',
    tooltip: 'Keep only top k legs at each pivot by counter-trend size (heft). 0 = disabled.',
    colorMode: 'restrictive-right',
  },
];

// Per-direction engulfed threshold slider
const ENGULFED_SLIDER: SliderConfig = {
  key: 'engulfed_breach_threshold',
  label: 'Engulfed',
  min: 0.0,
  max: 0.30,
  step: 0.01,
  description: 'Threshold for engulfed pruning',
  tooltip: 'Prune legs breached on both sides when combined breach exceeds this %. 0 = any breach triggers prune. 1.0 = disabled.',
  displayAsPercent: true,
  colorMode: 'restrictive-right',
};

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
  const [showTooltip, setShowTooltip] = useState<string | null>(null);
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
      localConfig.bull.engulfed_breach_threshold !== config.bull.engulfed_breach_threshold ||
      localConfig.bear.engulfed_breach_threshold !== config.bear.engulfed_breach_threshold ||
      localConfig.stale_extension_threshold !== config.stale_extension_threshold ||
      localConfig.origin_range_threshold !== config.origin_range_threshold ||
      localConfig.origin_time_threshold !== config.origin_time_threshold ||
      localConfig.max_turns !== config.max_turns
    );
  }, [localConfig, config]);

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
          engulfed_breach_threshold: localConfig.bull.engulfed_breach_threshold,
        },
        bear: {
          engulfed_breach_threshold: localConfig.bear.engulfed_breach_threshold,
        },
        stale_extension_threshold: localConfig.stale_extension_threshold,
        origin_range_threshold: localConfig.origin_range_threshold,
        origin_time_threshold: localConfig.origin_time_threshold,
        max_turns: localConfig.max_turns,
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
    const positionRatio = slider.max > slider.min ? (value - slider.min) / (slider.max - slider.min) : 0;

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
    const sliderKey = `${direction}-${slider.key}`;

    return (
      <div key={sliderKey} className="space-y-1">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            <span className="text-xs text-app-muted">
              {slider.label}
            </span>
            <button
              onClick={() => setShowTooltip(showTooltip === sliderKey ? null : sliderKey)}
              className="text-app-muted hover:text-app-text transition-colors"
              title={slider.tooltip}
            >
              <Info size={12} />
            </button>
          </div>
          <span
            className={`text-xs font-mono ${isDefault ? 'text-app-muted' : ''}`}
            style={!isDefault ? { color: sliderColor } : undefined}
          >
            {displayValue}
          </span>
        </div>
        {showTooltip === sliderKey && (
          <p className="text-xs text-app-muted bg-app-bg-tertiary p-2 rounded mb-1">
            {slider.tooltip}
          </p>
        )}
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

      {/* Prune Thresholds Section */}
      <div className="space-y-2">
        <span className="text-xs font-medium text-app-text">Prune Thresholds</span>
        <div className="pl-4 space-y-3">
          {PRUNE_SLIDERS.map(slider => renderSlider('global', slider))}
        </div>
      </div>

      {/* Direction-Specific Engulfed Thresholds */}
      <div className="space-y-2">
        <span className="text-xs font-medium text-app-text">Engulfed Threshold</span>
        <div className="pl-4 space-y-3">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs text-trading-bull font-medium">Bull</span>
            <span className="text-xs text-app-muted">|</span>
            <span className="text-xs text-trading-bear font-medium">Bear</span>
          </div>
          {renderSlider('bull', { ...ENGULFED_SLIDER, label: 'Bull' })}
          {renderSlider('bear', { ...ENGULFED_SLIDER, label: 'Bear' })}
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
