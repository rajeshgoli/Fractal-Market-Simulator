import React, { useState, useCallback } from 'react';
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
}

// Slider configurations for direction-specific parameters
const DIRECTION_SLIDERS: SliderConfig[] = [
  { key: 'formation_fib', label: 'Formation', min: 0.1, max: 1.0, step: 0.01, description: 'Retracement required to form leg' },
  { key: 'invalidation_threshold', label: 'Invalidation', min: 0.1, max: 1.0, step: 0.01, description: 'Breach threshold for invalidation' },
];

// Slider configurations for global parameters
const GLOBAL_SLIDERS: SliderConfig[] = [
  { key: 'stale_extension_threshold', label: 'Stale Extension', min: 1.0, max: 5.0, step: 0.1, description: 'Extension multiple for stale pruning' },
  { key: 'origin_range_threshold', label: 'Origin Range %', min: 0.0, max: 0.5, step: 0.01, description: 'Range similarity threshold for origin-proximity pruning' },
  { key: 'origin_time_threshold', label: 'Origin Time %', min: 0.0, max: 0.5, step: 0.01, description: 'Time proximity threshold for origin-proximity pruning' },
];

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

interface DetectionConfigPanelProps {
  config: DetectionConfig;
  onConfigUpdate: (config: DetectionConfig) => void;
  isCalibrated: boolean;
  className?: string;
}

export const DetectionConfigPanel: React.FC<DetectionConfigPanelProps> = ({
  config,
  onConfigUpdate,
  isCalibrated,
  className = '',
}) => {
  const [isUpdating, setIsUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [localConfig, setLocalConfig] = useState<DetectionConfig>(config);
  const [hasChanges, setHasChanges] = useState(false);

  // Update local config when prop changes
  React.useEffect(() => {
    setLocalConfig(config);
    setHasChanges(false);
  }, [config]);

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
    setHasChanges(true);
    setError(null);
  }, []);

  const handleToggleChange = useCallback((key: keyof DetectionConfig, value: boolean) => {
    setLocalConfig(prev => ({ ...prev, [key]: value }));
    setHasChanges(true);
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
        // Pruning algorithm toggles
        enable_engulfed_prune: localConfig.enable_engulfed_prune,
        enable_inner_structure_prune: localConfig.enable_inner_structure_prune,
      };

      const updatedConfig = await updateDetectionConfig(request);
      onConfigUpdate(updatedConfig);
      setHasChanges(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update config');
    } finally {
      setIsUpdating(false);
    }
  }, [localConfig, isCalibrated, onConfigUpdate]);

  const handleReset = useCallback(() => {
    setLocalConfig(DEFAULT_DETECTION_CONFIG);
    setHasChanges(true);
    setError(null);
  }, []);

  const renderSlider = (
    direction: 'bull' | 'bear' | 'global',
    slider: SliderConfig
  ) => {
    const value = direction === 'global'
      ? (localConfig[slider.key as keyof DetectionConfig] as number)
      : localConfig[direction][slider.key as keyof typeof localConfig.bull];

    const defaultValue = direction === 'global'
      ? (DEFAULT_DETECTION_CONFIG[slider.key as keyof DetectionConfig] as number)
      : DEFAULT_DETECTION_CONFIG[direction][slider.key as keyof typeof DEFAULT_DETECTION_CONFIG.bull];

    const isDefault = Math.abs(value - defaultValue) < 0.001;

    return (
      <div key={`${direction}-${slider.key}`} className="space-y-1">
        <div className="flex items-center justify-between">
          <span className="text-xs text-app-muted" title={slider.description}>
            {slider.label}
          </span>
          <span className={`text-xs font-mono ${isDefault ? 'text-app-muted' : 'text-trading-blue'}`}>
            {value.toFixed(slider.step >= 0.1 ? 1 : 2)}
          </span>
        </div>
        <input
          type="range"
          min={slider.min}
          max={slider.max}
          step={slider.step}
          value={value}
          onChange={(e) => handleSliderChange(direction, slider.key, parseFloat(e.target.value))}
          className="w-full h-1.5 bg-app-border rounded-lg appearance-none cursor-pointer accent-trading-blue"
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

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Header */}
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

      {/* Bull Direction */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-trading-bull" />
          <span className="text-xs font-medium text-app-text">Bull</span>
        </div>
        <div className="pl-4 space-y-3">
          {DIRECTION_SLIDERS.map(slider => renderSlider('bull', slider))}
        </div>
      </div>

      {/* Bear Direction */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-trading-bear" />
          <span className="text-xs font-medium text-app-text">Bear</span>
        </div>
        <div className="pl-4 space-y-3">
          {DIRECTION_SLIDERS.map(slider => renderSlider('bear', slider))}
        </div>
      </div>

      {/* Global Thresholds */}
      <div className="space-y-2">
        <span className="text-xs font-medium text-app-text">Global</span>
        <div className="pl-4 space-y-3">
          {GLOBAL_SLIDERS.map(slider => renderSlider('global', slider))}
        </div>
      </div>

      {/* Pruning Algorithms */}
      <div className="space-y-2">
        <span className="text-xs font-medium text-app-text">Pruning Algorithms</span>
        <div className="pl-4 space-y-2">
          {PRUNE_TOGGLES.map(toggle => renderToggle(toggle))}
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
};
