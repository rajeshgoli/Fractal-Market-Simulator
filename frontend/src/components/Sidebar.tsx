import React, { useState, useRef, useEffect } from 'react';
import { DetectionConfig, LegEvent, HighlightedDagItem } from '../types';
import { Settings, ChevronDown, ChevronRight, RotateCcw } from 'lucide-react';
import { ReplayEvent, DagLeg } from '../lib/api';
import { AttachableItem } from './DAGStatePanel';
import { DetectionConfigPanel, DetectionConfigPanelHandle } from './DetectionConfigPanel';
import { FeedbackForm } from './FeedbackForm';
import type { FeedbackContext, DagContext } from './FeedbackForm';
import { LingerEventsPanel, DAG_LINGER_EVENTS } from './LingerEventsPanel';
import type { LingerEventConfig } from './LingerEventsPanel';
import { MarketStructurePanel } from './MarketStructurePanel';

// Re-export for convenience
export { DAG_LINGER_EVENTS };
export type { LingerEventConfig, DagContext };

interface SidebarProps {
  // Linger event toggles
  lingerEvents: LingerEventConfig[];
  onToggleLingerEvent: (eventId: string) => void;
  onResetDefaults: () => void;
  className?: string;

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

  // DAG context
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
  lingerEvents,
  onToggleLingerEvent,
  onResetDefaults,
  className = '',
  showFeedback = false,
  isLingering = false,
  lingerEvent,
  currentPlaybackBar,
  feedbackContext,
  onFeedbackFocus,
  onFeedbackBlur,
  onPausePlayback,
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

      {/* Feedback Section (always visible during playback) */}
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
          detectionConfig={detectionConfig}
        />
      )}

      {/* Market Structure - pinned to bottom */}
      {dagContext && (
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
