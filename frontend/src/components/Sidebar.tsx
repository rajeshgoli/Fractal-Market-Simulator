import React, { useState, useCallback, useRef, RefObject, useEffect, useMemo } from 'react';
import { toPng } from 'html-to-image';
import { PlaybackState, DetectionConfig, LegEvent, HighlightedDagItem } from '../types';
import { Toggle } from './ui/Toggle';
import { Filter, MessageSquare, Send, Pause, BarChart2, GitBranch, Paperclip, X, ChevronDown, ChevronRight, Settings, RotateCcw, Zap, Maximize2 } from 'lucide-react';
import { submitPlaybackFeedback, PlaybackFeedbackEventContext, PlaybackFeedbackSnapshot, ReplayEvent, DagLeg } from '../lib/api';
import { AttachableItem } from './DAGStatePanel';
import { LifecycleEventWithLegInfo } from '../hooks/useFollowLeg';
import { DetectionConfigPanel, DetectionConfigPanelHandle } from './DetectionConfigPanel';
import { calculateLegStats } from '../utils/legStatsUtils';
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
  { id: 'LEVEL_CROSS', label: 'Level Crossed', description: 'Pause on Fib level cross', isEnabled: false },
];

// Default linger events for DAG mode
export const DAG_LINGER_EVENTS: LingerEventConfig[] = [
  { id: 'LEG_CREATED', label: 'Leg Created', description: 'Pause when new leg is created', isEnabled: true },
  { id: 'LEG_PRUNED', label: 'Leg Pruned', description: 'Pause when leg is pruned', isEnabled: true },
  { id: 'LEG_INVALIDATED', label: 'Leg Invalidated', description: 'Pause when leg is invalidated', isEnabled: true },
  { id: 'SWING_FORMED', label: 'Swing Formed', description: 'Pause when swing is formed', isEnabled: true },
];

// Replay mode context (calibration-specific)
export interface ReplayContext {
  selectedSwing?: {
    id: string;
    scale: string;
    direction: string;
  };
  calibrationState: 'calibrating' | 'calibration_complete' | 'playing' | 'paused';
}

// DAG mode context - full data for feedback snapshots
export interface DagContextLeg {
  leg_id: string;
  direction: 'bull' | 'bear';
  pivot_price: number;
  pivot_index: number;
  origin_price: number;
  origin_index: number;
  range: number;  // |origin_price - pivot_price|
}

export interface DagContextPendingOrigin {
  price: number;
  bar_index: number;
}

export interface DagContext {
  activeLegs: DagContextLeg[];
  pendingOrigins: {
    bull: DagContextPendingOrigin | null;
    bear: DagContextPendingOrigin | null;
  };
}

interface FeedbackContext {
  // Playback state information
  playbackState: PlaybackState;
  calibrationPhase: 'calibrating' | 'calibration_complete' | 'playing' | 'paused';
  csvIndex: number;  // Authoritative CSV row index from backend (#297)
  calibrationBarCount: number;
  currentBarIndex: number;
  // Swing counts
  swingsFoundByScale: {
    XL: number;
    L: number;
    M: number;
    S: number;
  };
  // Event counts
  totalEvents: number;
  swingsInvalidated: number;
  swingsCompleted: number;
}

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
  screenshotTargetRef?: RefObject<HTMLElement | null>;

  // Linger enabled state - controls visibility of event filters
  lingerEnabled?: boolean;

  // Attachment support
  attachedItems: AttachableItem[];
  onDetachItem: (item: AttachableItem) => void;
  onClearAttachments: () => void;

  // Detection config panel (Issue #288)
  detectionConfig?: DetectionConfig;
  initialDetectionConfig?: DetectionConfig;  // Saved preferences for UI (not applied to BE until user clicks Apply)
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
  const [feedbackText, setFeedbackText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitStatus, setSubmitStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [hasAutopaused, setHasAutopaused] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const detectionConfigRef = useRef<DetectionConfigPanelHandle>(null);

  // Collapse state for sidebar sections (#310)
  const [isLingerEventsCollapsed, setIsLingerEventsCollapsed] = useState(false);
  const [isDetectionConfigCollapsed, setIsDetectionConfigCollapsed] = useState(false);
  const [isMarketStructureCollapsed, setIsMarketStructureCollapsed] = useState(false);

  // Compute leg statistics from events using shared utility
  const legStats = useMemo(() => calculateLegStats(legEvents, activeLegs), [legEvents, activeLegs]);

  // Top 5 biggest legs (by price range)
  const biggestLegs = useMemo(() => {
    return [...activeLegs]
      .map(leg => ({
        ...leg,
        range: Math.abs(leg.pivot_price - leg.origin_price),
      }))
      .filter(leg => leg.range > 0)
      .sort((a, b) => b.range - a.range)
      .slice(0, 5);
  }, [activeLegs]);

  // Top 5 most impulsive legs
  const mostImpulsiveLegs = useMemo(() => {
    return [...activeLegs]
      .filter(leg => leg.impulsiveness !== null && leg.impulsiveness > 0)
      .sort((a, b) => (b.impulsiveness ?? 0) - (a.impulsiveness ?? 0))
      .slice(0, 5);
  }, [activeLegs]);

  // Auto-collapse/expand Detection Config based on linger state (#310)
  useEffect(() => {
    if (lingerEnabled) {
      // Collapse when linger enabled (less real estate)
      setIsDetectionConfigCollapsed(true);
    } else {
      // Expand when linger disabled (more real estate available)
      setIsDetectionConfigCollapsed(false);
    }
  }, [lingerEnabled]);

  const handleFeedbackSubmit = useCallback(async () => {
    if (!feedbackText.trim() || currentPlaybackBar === undefined || !feedbackContext) return;

    setIsSubmitting(true);
    setSubmitStatus('idle');

    try {
      // Build rich context snapshot
      const snapshot: PlaybackFeedbackSnapshot = {
        state: feedbackContext.calibrationPhase,
        csv_index: feedbackContext.csvIndex,  // Authoritative CSV index from backend (#297)
        bars_since_calibration: feedbackContext.currentBarIndex - feedbackContext.calibrationBarCount,
        current_bar_index: feedbackContext.currentBarIndex,
        calibration_bar_count: feedbackContext.calibrationBarCount,
        swings_found: feedbackContext.swingsFoundByScale,
        swings_invalidated: feedbackContext.swingsInvalidated,
        swings_completed: feedbackContext.swingsCompleted,
        // Add mode to context
        mode,
      };

      // Add event context if we have a linger event
      if (lingerEvent) {
        const eventContext: PlaybackFeedbackEventContext = {
          event_type: lingerEvent.type,
          scale: lingerEvent.scale,
        };

        if (lingerEvent.swing) {
          eventContext.swing = {
            high_bar_index: lingerEvent.swing.high_bar_index,
            low_bar_index: lingerEvent.swing.low_bar_index,
            high_price: String(lingerEvent.swing.high_price),
            low_price: String(lingerEvent.swing.low_price),
            direction: lingerEvent.swing.direction,
          };
          eventContext.detection_bar_index = lingerEvent.bar_index;
        }

        snapshot.event_context = eventContext;
      }

      // Add mode-specific context
      if (mode === 'replay' && replayContext) {
        snapshot.replay_context = {
          selected_swing: replayContext.selectedSwing,
          calibration_state: replayContext.calibrationState,
        };
      } else if (mode === 'dag' && dagContext) {
        snapshot.dag_context = {
          active_legs: dagContext.activeLegs.map(leg => ({
            leg_id: leg.leg_id,
            direction: leg.direction,
            pivot_price: leg.pivot_price,
            pivot_index: leg.pivot_index,
            origin_price: leg.origin_price,
            origin_index: leg.origin_index,
            range: leg.range,
          })),
          pending_origins: {
            bull: dagContext.pendingOrigins.bull
              ? { price: dagContext.pendingOrigins.bull.price, bar_index: dagContext.pendingOrigins.bull.bar_index }
              : null,
            bear: dagContext.pendingOrigins.bear
              ? { price: dagContext.pendingOrigins.bear.price, bar_index: dagContext.pendingOrigins.bear.bar_index }
              : null,
          },
        };
      }

      // Add attachments if any
      if (attachedItems && attachedItems.length > 0) {
        snapshot.attachments = attachedItems.map(item => {
          if (item.type === 'leg') {
            const leg = item.data as DagLeg;
            return {
              type: 'leg' as const,
              leg_id: leg.leg_id,
              direction: leg.direction,
              pivot_price: leg.pivot_price,
              origin_price: leg.origin_price,
              pivot_index: leg.pivot_index,
              origin_index: leg.origin_index,
            };
          } else if (item.type === 'pending_origin') {
            const pending = item.data as { price: number; bar_index: number; direction: 'bull' | 'bear'; source: string };
            return {
              type: 'pending_origin' as const,
              direction: pending.direction,
              price: pending.price,
              bar_index: pending.bar_index,
              source: pending.source,
            };
          } else {
            // lifecycle_event
            const event = item.data as LifecycleEventWithLegInfo;
            return {
              type: 'lifecycle_event' as const,
              leg_id: event.leg_id,
              leg_direction: event.legDirection,
              event_type: event.event_type,
              bar_index: event.bar_index,
              csv_index: event.csv_index,
              timestamp: event.timestamp,
              explanation: event.explanation,
            };
          }
        });
      }

      // Add detection config for reproducibility (#320)
      if (detectionConfig) {
        snapshot.detection_config = {
          bull: {
            formation_fib: detectionConfig.bull.formation_fib,
            engulfed_breach_threshold: detectionConfig.bull.engulfed_breach_threshold,
          },
          bear: {
            formation_fib: detectionConfig.bear.formation_fib,
            engulfed_breach_threshold: detectionConfig.bear.engulfed_breach_threshold,
          },
          stale_extension_threshold: detectionConfig.stale_extension_threshold,
          origin_range_threshold: detectionConfig.origin_range_threshold,
          origin_time_threshold: detectionConfig.origin_time_threshold,
          min_branch_ratio: detectionConfig.min_branch_ratio,
          min_turn_ratio: detectionConfig.min_turn_ratio,
          enable_engulfed_prune: detectionConfig.enable_engulfed_prune,
          enable_inner_structure_prune: detectionConfig.enable_inner_structure_prune,
        };
      }

      // Capture screenshot if target ref is available
      let screenshotData: string | undefined;
      if (screenshotTargetRef?.current) {
        try {
          const dataUrl = await toPng(screenshotTargetRef.current, {
            backgroundColor: '#1a1a2e', // Match app background
            pixelRatio: 1, // Use 1x scale for reasonable file size
          });
          screenshotData = dataUrl.split(',')[1]; // Get base64 without prefix
        } catch (err) {
          console.warn('Failed to capture screenshot:', err);
          // Continue without screenshot
        }
      }

      await submitPlaybackFeedback(feedbackText, currentPlaybackBar, snapshot, screenshotData);
      setFeedbackText('');
      onClearAttachments(); // Clear attachments after successful submit
      setSubmitStatus('success');
      setHasAutopaused(false); // Reset autopause state after successful submit
      // Clear success status after 2 seconds
      setTimeout(() => setSubmitStatus('idle'), 2000);
    } catch (err) {
      console.error('Failed to submit feedback:', err);
      setSubmitStatus('error');
      // Clear error status after 3 seconds
      setTimeout(() => setSubmitStatus('idle'), 3000);
    } finally {
      setIsSubmitting(false);
    }
  }, [feedbackText, lingerEvent, currentPlaybackBar, feedbackContext, mode, replayContext, dagContext, screenshotTargetRef, attachedItems, onClearAttachments, detectionConfig]);

  const handleInputFocus = useCallback(() => {
    // Pause linger timer if lingering
    onFeedbackFocus?.();
    // Auto-pause playback if playing (not lingering)
    if (!isLingering && feedbackContext?.playbackState === PlaybackState.PLAYING) {
      onPausePlayback?.();
      setHasAutopaused(true);
    }
  }, [onFeedbackFocus, isLingering, feedbackContext?.playbackState, onPausePlayback]);

  const handleInputBlur = useCallback(() => {
    onFeedbackBlur?.();
  }, [onFeedbackBlur]);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setFeedbackText(e.target.value);
    // Auto-pause on first keystroke if playing
    if (!hasAutopaused && !isLingering && feedbackContext?.playbackState === PlaybackState.PLAYING) {
      onPausePlayback?.();
      setHasAutopaused(true);
    }
  }, [hasAutopaused, isLingering, feedbackContext?.playbackState, onPausePlayback]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    // Submit on Ctrl+Enter or Cmd+Enter
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleFeedbackSubmit();
    }
  }, [handleFeedbackSubmit]);

  return (
    <aside className={`flex flex-col bg-app-secondary border-r border-app-border h-full ${className}`}>
      {/* Linger Event Toggles - only shown when linger is enabled */}
      {lingerEnabled && (
        <>
        {/* Sidebar Header - collapsible (#310) */}
        <button
          className="w-full p-4 border-b border-app-border hover:bg-app-card/30 transition-colors"
          onClick={() => {
            const willOpen = isLingerEventsCollapsed;
            setIsLingerEventsCollapsed(!isLingerEventsCollapsed);
            // Close Detection Config when opening this section (mutually exclusive)
            if (willOpen) setIsDetectionConfigCollapsed(true);
          }}
        >
          <h2 className="text-xs font-bold text-app-muted uppercase tracking-wider flex items-center gap-2">
            {isLingerEventsCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
            <Filter size={14} />
            {mode === 'dag' ? 'Structure Events' : 'Linger Events'}
          </h2>
        </button>

        {/* Event toggles - collapsible (#310) */}
        {!isLingerEventsCollapsed && (
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
      )}

      {/* Detection Config Panel (Issue #288) - collapsible (#310), adjacent to linger events */}
      {detectionConfig && onDetectionConfigUpdate && (
        <div className="border-t border-app-border">
          <div className="flex items-center">
            <button
              className="flex-1 p-4 hover:bg-app-card/30 transition-colors text-left"
              onClick={() => {
                const willOpen = isDetectionConfigCollapsed;
                setIsDetectionConfigCollapsed(!isDetectionConfigCollapsed);
                // Close Structure Events when opening this section (mutually exclusive)
                if (willOpen) setIsLingerEventsCollapsed(true);
              }}
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
      {showFeedback && feedbackContext && (
        <div className="p-4 border-t border-app-border bg-app-bg/30">
          <h2 className="text-xs font-bold text-app-muted uppercase tracking-wider flex items-center gap-2 mb-3">
            <MessageSquare size={14} />
            Observation
            {attachedItems && attachedItems.length > 0 && (
              <span className="flex items-center gap-1 text-trading-purple">
                <Paperclip size={10} />
                <span className="text-[10px] font-normal normal-case">{attachedItems.length}/5</span>
              </span>
            )}
            {hasAutopaused && (
              <span className="flex items-center gap-1 text-trading-orange">
                <Pause size={10} />
                <span className="text-[10px] font-normal normal-case">paused</span>
              </span>
            )}
          </h2>

          {/* Attached Items Display */}
          {attachedItems && attachedItems.length > 0 && (
            <div className="mb-3 space-y-1">
              {attachedItems.map((item, idx) => {
                let label = '';
                let colorClass = '';
                if (item.type === 'leg') {
                  const leg = item.data as DagLeg;
                  label = `${leg.direction.toUpperCase()} Leg @${leg.pivot_index}`;
                  colorClass = leg.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear';
                } else if (item.type === 'pending_origin') {
                  const pending = item.data as { price: number; bar_index: number; direction: 'bull' | 'bear' };
                  label = `${pending.direction.toUpperCase()} Pending @${pending.bar_index}`;
                  colorClass = pending.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear';
                } else {
                  // lifecycle_event
                  const event = item.data as LifecycleEventWithLegInfo;
                  const eventName = event.event_type.replace('_', ' ').toUpperCase();
                  label = `${event.legDirection.toUpperCase()} ${eventName} @${event.bar_index}`;
                  colorClass = event.legDirection === 'bull' ? 'text-trading-bull' : 'text-trading-bear';
                }
                return (
                  <div
                    key={idx}
                    className="flex items-center justify-between text-xs bg-trading-purple/10 rounded px-2 py-1 border border-trading-purple/30"
                  >
                    <span className={colorClass}>{label}</span>
                    <button
                      onClick={() => onDetachItem(item)}
                      className="text-app-muted hover:text-trading-bear transition-colors"
                    >
                      <X size={12} />
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          <div className="space-y-2">
            <textarea
              ref={inputRef}
              value={feedbackText}
              onChange={handleInputChange}
              onFocus={handleInputFocus}
              onBlur={handleInputBlur}
              onKeyDown={handleKeyDown}
              placeholder="Type observation... (Ctrl+Enter to submit)"
              className="w-full h-32 px-3 py-2 text-sm bg-app-card border border-app-border rounded resize-none focus:outline-none focus:border-trading-blue placeholder:text-app-muted"
              disabled={isSubmitting}
            />
            <div className="flex items-center justify-between">
              <span className={`text-xs ${
                submitStatus === 'success' ? 'text-trading-bull' :
                submitStatus === 'error' ? 'text-trading-bear' :
                'text-app-muted'
              }`}>
                {submitStatus === 'success' && 'Saved!'}
                {submitStatus === 'error' && 'Failed to save'}
                {submitStatus === 'idle' && isLingering && lingerEvent?.scale && `${lingerEvent.scale} - ${lingerEvent.type}`}
                {submitStatus === 'idle' && !isLingering && `Bar ${feedbackContext.currentBarIndex}`}
              </span>
              <button
                onClick={handleFeedbackSubmit}
                disabled={isSubmitting || !feedbackText.trim()}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded transition-colors ${
                  isSubmitting || !feedbackText.trim()
                    ? 'bg-app-border text-app-muted cursor-not-allowed'
                    : 'bg-trading-blue text-white hover:bg-blue-600'
                }`}
              >
                <Send size={12} />
                {isSubmitting ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Market Structure (DAG mode only) - pinned to bottom */}
      {mode === 'dag' && dagContext && (
        <div className="border-t border-app-border mt-auto">
          <button
            className="w-full p-3 hover:bg-app-card/30 transition-colors"
            onClick={() => setIsMarketStructureCollapsed(!isMarketStructureCollapsed)}
          >
            <h2 className="text-xs font-bold text-app-muted uppercase tracking-wider flex items-center gap-2">
              {isMarketStructureCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
              <GitBranch size={14} />
              Market Structure
            </h2>
          </button>

          {!isMarketStructureCollapsed && (
            <div className="px-3 pb-3 space-y-3">
              {/* Current State + Pruning Stats - compact side by side */}
              <div className="grid grid-cols-2 gap-3 text-[10px]">
                <div className="space-y-0.5">
                  <div className="flex justify-between">
                    <span className="text-app-muted">Active</span>
                    <span className="text-app-text font-medium">{dagContext.activeLegs.length}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-app-muted">Formed</span>
                    <span className="text-trading-bull font-medium">{legStats.formed}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-app-muted">Invalidated</span>
                    <span className="text-trading-bear font-medium">{legStats.invalidated}</span>
                  </div>
                </div>
                <div className="space-y-0.5">
                  <div className="flex justify-between">
                    <span className="text-app-muted">Engulfed</span>
                    <span className="text-trading-orange font-medium">{legStats.engulfed}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-app-muted">Proximity</span>
                    <span className="text-app-text font-medium">{legStats.proximity}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-app-muted">CTR</span>
                    <span className="text-app-text font-medium">{legStats.minCtr}</span>
                  </div>
                </div>
              </div>

              {/* Top Legs - side by side */}
              {(biggestLegs.length > 0 || mostImpulsiveLegs.length > 0) && (
                <div className="grid grid-cols-2 gap-3">
                  {/* Biggest (by range) */}
                  {biggestLegs.length > 0 && (
                    <div>
                      <h3 className="text-[10px] font-bold text-app-muted uppercase tracking-wider mb-1 flex items-center gap-1">
                        <Maximize2 size={10} />
                        Biggest
                      </h3>
                      <div className="space-y-0.5 text-[10px]">
                        {biggestLegs.map((leg) => {
                          const isHighlighted = highlightedItem?.type === 'leg' && highlightedItem.id === leg.leg_id;
                          return (
                            <div
                              key={leg.leg_id}
                              className={`flex items-center justify-between px-1 py-0.5 rounded cursor-pointer transition-colors ${
                                isHighlighted ? 'bg-trading-blue/30 ring-1 ring-trading-blue' : 'hover:bg-app-card/50'
                              }`}
                              onMouseEnter={() => onHoverLeg?.({ type: 'leg', id: leg.leg_id, direction: leg.direction })}
                              onMouseLeave={() => onHoverLeg?.(null)}
                            >
                              <span className={`${leg.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}`}>
                                {leg.direction.charAt(0).toUpperCase()}
                              </span>
                              <span className="text-app-muted font-mono">
                                {leg.range.toFixed(2)}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Most Impulsive */}
                  {mostImpulsiveLegs.length > 0 && (
                    <div>
                      <h3 className="text-[10px] font-bold text-app-muted uppercase tracking-wider mb-1 flex items-center gap-1">
                        <Zap size={10} />
                        Impulsive
                      </h3>
                      <div className="space-y-0.5 text-[10px]">
                        {mostImpulsiveLegs.map((leg) => {
                          const isHighlighted = highlightedItem?.type === 'leg' && highlightedItem.id === leg.leg_id;
                          return (
                            <div
                              key={leg.leg_id}
                              className={`flex items-center justify-between px-1 py-0.5 rounded cursor-pointer transition-colors ${
                                isHighlighted ? 'bg-trading-blue/30 ring-1 ring-trading-blue' : 'hover:bg-app-card/50'
                              }`}
                              onMouseEnter={() => onHoverLeg?.({ type: 'leg', id: leg.leg_id, direction: leg.direction })}
                              onMouseLeave={() => onHoverLeg?.(null)}
                            >
                              <span className={`${leg.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear'}`}>
                                {leg.direction.charAt(0).toUpperCase()}
                              </span>
                              <span className="text-app-muted font-mono">
                                {(leg.impulsiveness ?? 0).toFixed(1)}%
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
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
