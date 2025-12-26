import React, { useState, useRef, useEffect } from 'react';
import { DetectionConfig, LegEvent, HighlightedDagItem } from '../types';
import { BarChart2, Settings, ChevronDown, ChevronRight, RotateCcw } from 'lucide-react';
import { Toggle } from './ui/Toggle';
import { ReplayEvent, DagLeg } from '../lib/api';
import { AttachableItem } from './DAGStatePanel';
import { DetectionConfigPanel, DetectionConfigPanelHandle } from './DetectionConfigPanel';
import { FeedbackForm } from './FeedbackForm';
import type { FeedbackContext, ReplayContext, DagContext } from './FeedbackForm';
import { LingerEventsPanel, REPLAY_LINGER_EVENTS, DAG_LINGER_EVENTS } from './LingerEventsPanel';
import type { LingerEventConfig } from './LingerEventsPanel';
import { MarketStructurePanel } from './MarketStructurePanel';

// Re-export for backward compatibility
export { REPLAY_LINGER_EVENTS, DAG_LINGER_EVENTS };
export type { LingerEventConfig, DagContext, ReplayContext };

interface SidebarProps {
  // Mode selection
  mode: 'replay' | 'dag';

  // Linger event toggles (mode-specific)
  lingerEvents: LingerEventConfig[];
  onToggleLingerEvent: (eventId: string) => void;
  onResetDefaults: () => void;
  className?: string;

  // Stats panel toggle (shown during playback, replay mode only)
  showStatsToggle?: boolean;
  showStats?: boolean;
  onToggleShowStats?: () => void;

  // Feedback props - now always visible during playback
  showFeedback?: boolean;
  isLingering?: boolean;
  lingerEvent?: ReplayEvent;
  currentPlaybackBar?: number;
  feedbackContext?: FeedbackContext;
  onFeedbackFocus?: () => void;
  onFeedbackBlur?: () => void;

  // Pause playback on typing (for non-linger state)
  onPausePlayback?: () => void;

  // Mode-specific context
  replayContext?: ReplayContext;
  dagContext?: DagContext;

  // Screenshot capture target (main content area)
  screenshotTargetRef?: React.RefObject<HTMLElement | null>;

  // Linger enabled state - controls visibility of event filters
  lingerEnabled?: boolean;

  // Attachment support
  attachedItems: AttachableItem[];
  onDetachItem: (item: AttachableItem) => void;
  onClearAttachments: () => void;

  // Detection config panel (Issue #288)
  detectionConfig?: DetectionConfig;
  initialDetectionConfig?: DetectionConfig;
  onDetectionConfigUpdate?: (config: DetectionConfig) => void;
  isCalibrated?: boolean;

  // Market Structure stats props
  legEvents?: LegEvent[];
  activeLegs?: DagLeg[];

  // Leg highlight support (from DAGStatePanel pattern)
  onHoverLeg?: (item: HighlightedDagItem | null) => void;
  highlightedItem?: HighlightedDagItem | null;
}

export const Sidebar: React.FC<SidebarProps> = ({
  mode,
  lingerEvents,
  onToggleLingerEvent,
  onResetDefaults,
  className = '',
  showStatsToggle = false,
  showStats = false,
  onToggleShowStats,
  showFeedback = false,
  isLingering = false,
  lingerEvent,
  currentPlaybackBar,
  feedbackContext,
  onFeedbackFocus,
  onFeedbackBlur,
  onPausePlayback,
  replayContext,
  dagContext,
  screenshotTargetRef,
  lingerEnabled = true,
  attachedItems,
  onDetachItem,
  onClearAttachments,
  detectionConfig,
  initialDetectionConfig,
  onDetectionConfigUpdate,
  isCalibrated = false,
  legEvents = [],
  activeLegs = [],
  onHoverLeg,
  highlightedItem,
}) => {
  const detectionConfigRef = useRef<DetectionConfigPanelHandle>(null);

  // Collapse state for sidebar sections
  const [isLingerEventsCollapsed, setIsLingerEventsCollapsed] = useState(false);
  const [isDetectionConfigCollapsed, setIsDetectionConfigCollapsed] = useState(false);
  const [isMarketStructureCollapsed, setIsMarketStructureCollapsed] = useState(false);

  // Auto-collapse/expand Detection Config based on linger state
  useEffect(() => {
    if (lingerEnabled) {
      setIsDetectionConfigCollapsed(true);
    } else {
      setIsDetectionConfigCollapsed(false);
    }
  }, [lingerEnabled]);

  // Handle linger events panel toggle
  const handleLingerEventsToggle = () => {
    const willOpen = isLingerEventsCollapsed;
    setIsLingerEventsCollapsed(!isLingerEventsCollapsed);
    // Close Detection Config when opening this section (mutually exclusive)
    if (willOpen) setIsDetectionConfigCollapsed(true);
  };

  // Handle detection config panel toggle
  const handleDetectionConfigToggle = () => {
    const willOpen = isDetectionConfigCollapsed;
    setIsDetectionConfigCollapsed(!isDetectionConfigCollapsed);
    // Close Structure Events when opening this section (mutually exclusive)
    if (willOpen) setIsLingerEventsCollapsed(true);
  };

  return (
    <aside className={`flex flex-col bg-app-secondary border-r border-app-border h-full ${className}`}>
      {/* Linger Event Toggles - only shown when linger is enabled */}
      {lingerEnabled && (
        <LingerEventsPanel
          mode={mode}
          lingerEvents={lingerEvents}
          onToggleLingerEvent={onToggleLingerEvent}
          isCollapsed={isLingerEventsCollapsed}
          onToggleCollapse={handleLingerEventsToggle}
        />
      )}

      {/* Detection Config Panel - collapsible, adjacent to linger events */}
      {detectionConfig && onDetectionConfigUpdate && (
        <div className="border-t border-app-border">
          <div className="flex items-center">
            <button
              className="flex-1 p-4 hover:bg-app-card/30 transition-colors text-left"
              onClick={handleDetectionConfigToggle}
            >
              <h3 className="text-xs font-bold text-app-muted uppercase tracking-wider flex items-center gap-2">
                {isDetectionConfigCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                <Settings size={14} />
                Detection Config
              </h3>
            </button>
            <button
              onClick={() => detectionConfigRef.current?.reset()}
              className="p-4 text-app-muted hover:text-white transition-colors"
              title="Reset to defaults"
            >
              <RotateCcw size={14} />
            </button>
          </div>
          {!isDetectionConfigCollapsed && (
            <div className="px-4 pb-4">
              <DetectionConfigPanel
                ref={detectionConfigRef}
                config={detectionConfig}
                initialLocalConfig={initialDetectionConfig}
                onConfigUpdate={onDetectionConfigUpdate}
                isCalibrated={isCalibrated}
                hideHeader={true}
              />
            </div>
          )}
        </div>
      )}

      {/* Show Stats Toggle (shown during playback, replay mode only) */}
      {showStatsToggle && onToggleShowStats && (
        <div className="p-4 border-t border-app-border">
          <div
            className={`
              group flex items-start gap-3 p-3 rounded-lg transition-all duration-200
              ${showStats
                ? 'bg-app-card border border-app-border'
                : 'hover:bg-app-card/50 border border-transparent opacity-70'
              }
            `}
          >
            <div className="pt-1">
              <BarChart2 size={16} className="text-trading-purple" />
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between mb-1">
                <span className={`text-sm font-medium ${showStats ? 'text-app-text' : 'text-app-muted'}`}>
                  Show Stats
                </span>
                <Toggle
                  checked={showStats}
                  onChange={onToggleShowStats}
                  id="toggle-show-stats"
                />
              </div>
              <p className="text-xs text-app-muted">
                Show calibration stats panel during playback
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Feedback Section (always visible during playback) */}
      {showFeedback && feedbackContext && currentPlaybackBar !== undefined && (
        <FeedbackForm
          mode={mode}
          isLingering={isLingering}
          lingerEvent={lingerEvent}
          currentPlaybackBar={currentPlaybackBar}
          feedbackContext={feedbackContext}
          onFeedbackFocus={onFeedbackFocus}
          onFeedbackBlur={onFeedbackBlur}
          onPausePlayback={onPausePlayback}
          replayContext={replayContext}
          dagContext={dagContext}
          screenshotTargetRef={screenshotTargetRef}
          attachedItems={attachedItems}
          onDetachItem={onDetachItem}
          onClearAttachments={onClearAttachments}
          detectionConfig={detectionConfig}
        />
      )}

      {/* Market Structure (DAG mode only) - pinned to bottom */}
      {mode === 'dag' && dagContext && (
        <MarketStructurePanel
          dagContext={dagContext}
          legEvents={legEvents}
          activeLegs={activeLegs}
          isCollapsed={isMarketStructureCollapsed}
          onToggleCollapse={() => setIsMarketStructureCollapsed(!isMarketStructureCollapsed)}
          onHoverLeg={onHoverLeg}
          highlightedItem={highlightedItem}
        />
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
