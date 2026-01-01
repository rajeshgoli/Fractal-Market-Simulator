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
  tooltip: string;
  displayAsPercent?: boolean;
  colorMode?: 'restrictive-right' | 'restrictive-left';
}

// Discrete Fib values for engulfed slider
const ENGULFED_FIB_VALUES = [0, 0.236, 0.382, 0.5, 0.618, 1];

// Find nearest Fib value
function nearestFib(value: number): number {
  let nearest = ENGULFED_FIB_VALUES[0];
  let minDiff = Math.abs(value - nearest);
  for (const fib of ENGULFED_FIB_VALUES) {
    const diff = Math.abs(value - fib);
    if (diff < minDiff) {
      minDiff = diff;
      nearest = fib;
    }
  }
  return nearest;
}

interface DetectionConfigPanelProps {
  config: DetectionConfig;
  onConfigUpdate: (config: DetectionConfig) => void;
  isCalibrated: boolean;
  className?: string;
  hideHeader?: boolean;
  initialLocalConfig?: DetectionConfig;
}

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
  const [localConfig, setLocalConfig] = useState<DetectionConfig>(
    initialLocalConfig ?? config
  );

  const hasAppliedRef = React.useRef(false);

  React.useEffect(() => {
    if (hasAppliedRef.current) {
      setLocalConfig(config);
      hasAppliedRef.current = false;
    }
  }, [config]);

  const hasChanges = useMemo(() => {
    return (
      localConfig.engulfed_breach_threshold !== config.engulfed_breach_threshold ||
      localConfig.stale_extension_threshold !== config.stale_extension_threshold ||
      localConfig.origin_range_threshold !== config.origin_range_threshold ||
      localConfig.origin_time_threshold !== config.origin_time_threshold ||
      localConfig.max_turns !== config.max_turns
    );
  }, [localConfig, config]);

  const handleSliderChange = useCallback((key: string, value: number) => {
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
      const request: DetectionConfigUpdateRequest = {
        stale_extension_threshold: localConfig.stale_extension_threshold,
        origin_range_threshold: localConfig.origin_range_threshold,
        origin_time_threshold: localConfig.origin_time_threshold,
        max_turns: localConfig.max_turns,
        engulfed_breach_threshold: localConfig.engulfed_breach_threshold,
      };

      const updatedConfig = await updateDetectionConfig(request);
      hasAppliedRef.current = true;
      onConfigUpdate(updatedConfig);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update config');
    } finally {
      setIsUpdating(false);
    }
  }, [localConfig, isCalibrated, onConfigUpdate]);

  const handleReset = useCallback(() => {
    setLocalConfig(DEFAULT_DETECTION_CONFIG);
    setError(null);
  }, []);

  useImperativeHandle(ref, () => ({
    reset: handleReset,
  }), [handleReset]);

  // Get slider color based on value position
  const getSliderColor = (value: number, min: number, max: number, colorMode: 'restrictive-right' | 'restrictive-left') => {
    const positionRatio = max > min ? (value - min) / (max - min) : 0;
    const ratio = colorMode === 'restrictive-right' ? positionRatio : 1 - positionRatio;
    const r = Math.round(34 + ratio * (239 - 34));
    const g = Math.round(197 - ratio * (197 - 68));
    const b = Math.round(94 - ratio * (94 - 68));
    return `rgb(${r}, ${g}, ${b})`;
  };

  // Render continuous slider
  const renderSlider = (slider: SliderConfig) => {
    const value = localConfig[slider.key as keyof DetectionConfig] as number ?? 0;
    const defaultValue = DEFAULT_DETECTION_CONFIG[slider.key as keyof DetectionConfig] as number;
    const isDefault = Math.abs(value - defaultValue) < 0.001;

    const displayValue = slider.displayAsPercent
      ? `${Math.round(value * 100)}%`
      : slider.step >= 1 ? String(Math.round(value)) : value.toFixed(slider.step >= 0.1 ? 1 : 2);

    const sliderColor = slider.colorMode
      ? getSliderColor(value, slider.min, slider.max, slider.colorMode)
      : 'rgb(59, 130, 246)';

    return (
      <div key={slider.key} className="space-y-1">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            <span className="text-xs text-app-muted">{slider.label}</span>
            <button
              onClick={() => setShowTooltip(showTooltip === slider.key ? null : slider.key)}
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
        {showTooltip === slider.key && (
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
          onChange={(e) => handleSliderChange(slider.key, parseFloat(e.target.value))}
          className="w-full h-1.5 bg-app-border rounded-lg appearance-none cursor-pointer"
          style={{ accentColor: sliderColor }}
          disabled={isUpdating}
        />
      </div>
    );
  };

  // Render engulfed slider with discrete Fib values
  const renderEngulfedSlider = () => {
    const value = localConfig.engulfed_breach_threshold;
    const defaultValue = DEFAULT_DETECTION_CONFIG.engulfed_breach_threshold;
    const isDefault = Math.abs(value - defaultValue) < 0.001;
    const sliderIndex = ENGULFED_FIB_VALUES.indexOf(nearestFib(value));

    // Color: 0 = most restrictive (red), 1 = least restrictive (green)
    const ratio = value; // 0 to 1
    const r = Math.round(239 - ratio * (239 - 34));
    const g = Math.round(68 + ratio * (197 - 68));
    const b = Math.round(68 + ratio * (94 - 68));
    const sliderColor = `rgb(${r}, ${g}, ${b})`;

    const displayValue = value === 0 ? '0' : value === 1 ? 'Off' : value.toFixed(3);

    return (
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            <span className="text-xs text-app-muted">Engulfed</span>
            <button
              onClick={() => setShowTooltip(showTooltip === 'engulfed' ? null : 'engulfed')}
              className="text-app-muted hover:text-app-text transition-colors"
              title="Retain engulfed legs until breach exceeds this fraction of range. 0 = immediate prune. 1 = disabled."
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
        {showTooltip === 'engulfed' && (
          <p className="text-xs text-app-muted bg-app-bg-tertiary p-2 rounded mb-1">
            Retain engulfed legs until breach exceeds this fraction of range. 0 = immediate prune (most aggressive). 1 = disabled (no engulfed pruning).
          </p>
        )}
        <input
          type="range"
          min={0}
          max={ENGULFED_FIB_VALUES.length - 1}
          step={1}
          value={sliderIndex}
          onChange={(e) => handleSliderChange('engulfed_breach_threshold', ENGULFED_FIB_VALUES[parseInt(e.target.value)])}
          className="w-full h-1.5 bg-app-border rounded-lg appearance-none cursor-pointer"
          style={{ accentColor: sliderColor }}
          disabled={isUpdating}
        />
        <div className="flex justify-between text-[9px] text-app-muted">
          <span>0</span>
          <span>.236</span>
          <span>.382</span>
          <span>.5</span>
          <span>.618</span>
          <span>Off</span>
        </div>
      </div>
    );
  };

  return (
    <div className={`space-y-4 ${className}`}>
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

      {/* Pruning Thresholds Section */}
      <div className="space-y-3">
        <span className="text-xs font-medium text-app-text">Pruning Thresholds</span>
        <div className="pl-4 space-y-3">
          {/* Engulfed - discrete Fib values */}
          {renderEngulfedSlider()}

          {/* Max Legs per Pivot */}
          {renderSlider({
            key: 'max_turns',
            label: 'Max Legs/Pivot',
            min: 0,
            max: 20,
            step: 1,
            description: 'Max legs per pivot',
            tooltip: 'Keep top N legs at each pivot, ranked by counter-trend range. 0 = no limit.',
            colorMode: 'restrictive-right',
          })}

          {/* Origin Proximity sub-section */}
          <div className="space-y-2 pt-1">
            <span className="text-[10px] font-medium text-app-muted uppercase">Origin Proximity</span>
            <div className="pl-2 space-y-3">
              {renderSlider({
                key: 'origin_range_threshold',
                label: 'Range %',
                min: 0.0,
                max: 0.10,
                step: 0.01,
                description: 'Range similarity threshold',
                tooltip: 'Legs within this range difference are candidates for consolidation. Works with Time % — both must match.',
                displayAsPercent: true,
                colorMode: 'restrictive-right',
              })}
              {renderSlider({
                key: 'origin_time_threshold',
                label: 'Time %',
                min: 0.0,
                max: 0.10,
                step: 0.01,
                description: 'Time proximity threshold',
                tooltip: 'Legs formed within this time window are candidates for consolidation. Works with Range % — both must match.',
                displayAsPercent: true,
                colorMode: 'restrictive-right',
              })}
            </div>
          </div>

          {/* Stale Extension */}
          {renderSlider({
            key: 'stale_extension_threshold',
            label: 'Stale Extension',
            min: 1.0,
            max: 5.0,
            step: 0.1,
            description: 'Prune extended legs',
            tooltip: 'Prune invalidated child legs after price moves this multiple of their range beyond origin.',
            colorMode: 'restrictive-left',
          })}
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

      {error && (
        <p className="text-xs text-trading-bear">{error}</p>
      )}
      {!isCalibrated && (
        <p className="text-xs text-app-muted">Calibrate first to enable config changes</p>
      )}
    </div>
  );
});
