import React from 'react';
import { Filter, ChevronDown, ChevronRight } from 'lucide-react';
import { Toggle } from './ui/Toggle';
import { getIconForEventType } from '../utils/eventTypeUtils';

// Linger event configuration for mode-specific toggles
export interface LingerEventConfig {
  id: string;
  label: string;
  description: string;
  isEnabled: boolean;
}

// Default linger events for Replay mode
export const REPLAY_LINGER_EVENTS: LingerEventConfig[] = [
  { id: 'SWING_FORMED', label: 'Swing Formed', description: 'Pause when swing is detected', isEnabled: true },
  { id: 'SWING_COMPLETED', label: 'Swing Completed', description: 'Pause when swing reaches target', isEnabled: true },
  { id: 'SWING_INVALIDATED', label: 'Swing Invalidated', description: 'Pause when swing is invalidated', isEnabled: true },
];

// Default linger events for DAG mode
export const DAG_LINGER_EVENTS: LingerEventConfig[] = [
  { id: 'LEG_CREATED', label: 'Leg Created', description: 'Pause when new leg is created', isEnabled: true },
  { id: 'LEG_PRUNED', label: 'Leg Pruned', description: 'Pause when leg is pruned', isEnabled: true },
  { id: 'LEG_INVALIDATED', label: 'Leg Invalidated', description: 'Pause when leg is invalidated', isEnabled: true },
  { id: 'SWING_FORMED', label: 'Swing Formed', description: 'Pause when swing is formed', isEnabled: true },
];

interface LingerEventsPanelProps {
  mode: 'replay' | 'dag';
  lingerEvents: LingerEventConfig[];
  onToggleLingerEvent: (eventId: string) => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export const LingerEventsPanel: React.FC<LingerEventsPanelProps> = ({
  mode,
  lingerEvents,
  onToggleLingerEvent,
  isCollapsed,
  onToggleCollapse,
}) => {
  return (
    <>
      <button
        className="w-full p-4 border-b border-app-border hover:bg-app-card/30 transition-colors"
        onClick={onToggleCollapse}
      >
        <h2 className="text-xs font-bold text-app-muted uppercase tracking-wider flex items-center gap-2">
          {isCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
          <Filter size={14} />
          {mode === 'dag' ? 'Structure Events' : 'Linger Events'}
        </h2>
      </button>

      {!isCollapsed && (
        <div className="flex-1 overflow-y-auto p-4 space-y-1">
          {lingerEvents.map((event) => (
            <div
              key={event.id}
              className={`
                group flex items-start gap-3 p-3 rounded-lg transition-all duration-200
                ${event.isEnabled
                  ? 'bg-app-card border border-app-border'
                  : 'hover:bg-app-card/50 border border-transparent opacity-70'
                }
              `}
            >
              <div className="pt-1">
                {getIconForEventType(event.id)}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-1">
                  <span className={`text-sm font-medium ${event.isEnabled ? 'text-app-text' : 'text-app-muted'}`}>
                    {event.label}
                  </span>
                  <Toggle
                    checked={event.isEnabled}
                    onChange={() => onToggleLingerEvent(event.id)}
                    id={`toggle-${event.id}`}
                  />
                </div>
                <p className="text-xs text-app-muted truncate group-hover:whitespace-normal group-hover:overflow-visible">
                  {event.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
};
