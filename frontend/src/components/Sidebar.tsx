import React from 'react';
import { FilterState, EventType, SwingDisplayConfig, SwingScaleKey } from '../types';
import { Toggle } from './ui/Toggle';
import { Filter, Activity, CheckCircle, XCircle, Eye, AlertTriangle, Layers } from 'lucide-react';

interface SidebarProps {
  filters: FilterState[];
  onToggleFilter: (id: string) => void;
  onResetDefaults: () => void;
  className?: string;
  // Scale filter props (shown during playback)
  showScaleFilters?: boolean;
  displayConfig?: SwingDisplayConfig;
  onToggleScale?: (scale: SwingScaleKey) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  filters,
  onToggleFilter,
  onResetDefaults,
  className = '',
  showScaleFilters = false,
  displayConfig,
  onToggleScale,
}) => {
  const scaleOrder: SwingScaleKey[] = ['XL', 'L', 'M', 'S'];
  const getIconForType = (type: string) => {
    switch (type) {
      case EventType.SWING_FORMED:
        return <Activity size={16} className="text-trading-purple" />;
      case EventType.COMPLETION:
        return <CheckCircle size={16} className="text-trading-bull" />;
      case EventType.INVALIDATION:
        return <XCircle size={16} className="text-trading-bear" />;
      case EventType.LEVEL_CROSS:
        return <Eye size={16} className="text-trading-blue" />;
      default:
        return <AlertTriangle size={16} className="text-trading-orange" />;
    }
  };

  return (
    <aside className={`flex flex-col bg-app-secondary border-r border-app-border h-full ${className}`}>
      {/* Sidebar Header */}
      <div className="p-4 border-b border-app-border">
        <h2 className="text-xs font-bold text-app-muted uppercase tracking-wider flex items-center gap-2">
          <Filter size={14} />
          Linger Events
        </h2>
      </div>

      {/* Filter List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-1">
        {filters.map((filter) => (
          <div
            key={filter.id}
            className={`
              group flex items-start gap-3 p-3 rounded-lg transition-all duration-200
              ${filter.isEnabled
                ? 'bg-app-card border border-app-border'
                : 'hover:bg-app-card/50 border border-transparent opacity-70'
              }
            `}
          >
            <div className="pt-1">
              {getIconForType(filter.id)}
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between mb-1">
                <span className={`text-sm font-medium ${filter.isEnabled ? 'text-app-text' : 'text-app-muted'}`}>
                  {filter.label}
                </span>
                <Toggle
                  checked={filter.isEnabled}
                  onChange={() => onToggleFilter(filter.id)}
                  id={`toggle-${filter.id}`}
                />
              </div>
              <p className="text-xs text-app-muted truncate group-hover:whitespace-normal group-hover:overflow-visible">
                {filter.description}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Scale Filters Section (shown during playback) */}
      {showScaleFilters && displayConfig && onToggleScale && (
        <div className="p-4 border-t border-app-border">
          <h2 className="text-xs font-bold text-app-muted uppercase tracking-wider flex items-center gap-2 mb-3">
            <Layers size={14} />
            Scale Filters
          </h2>
          <div className="flex flex-wrap gap-2">
            {scaleOrder.map(scale => {
              const isEnabled = displayConfig.enabledScales.has(scale);
              return (
                <label
                  key={scale}
                  className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded border cursor-pointer transition-colors ${
                    isEnabled
                      ? 'bg-trading-blue/20 border-trading-blue text-trading-blue'
                      : 'bg-app-card border-app-border text-app-muted hover:border-app-text/30'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isEnabled}
                    onChange={() => onToggleScale(scale)}
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
        </div>
      )}

      {/* Bottom Actions */}
      <div className="p-4 border-t border-app-border bg-app-bg/30">
        <button
          onClick={onResetDefaults}
          className="w-full text-xs text-app-muted hover:text-white text-center py-2 border border-dashed border-app-border rounded hover:border-app-muted transition-colors"
        >
          Reset to Defaults
        </button>
      </div>
    </aside>
  );
};
