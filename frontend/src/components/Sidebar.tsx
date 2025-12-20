import React, { useState, useCallback, useRef, RefObject } from 'react';
import { toPng } from 'html-to-image';
import { EventType, SwingDisplayConfig, SwingScaleKey, PlaybackState } from '../types';
import { Toggle } from './ui/Toggle';
import { Filter, Activity, CheckCircle, XCircle, Eye, AlertTriangle, Layers, MessageSquare, Send, Pause, BarChart2, GitBranch, Scissors, Ban } from 'lucide-react';
import { submitPlaybackFeedback, PlaybackFeedbackEventContext, PlaybackFeedbackSnapshot, ReplayEvent } from '../lib/api';

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

// DAG mode context
export interface DagContext {
  activeLegsCount: number;
  orphanedOriginsCount: { bull: number; bear: number };
  pendingPivotsCount: number;
}

interface FeedbackContext {
  // Playback state information
  playbackState: PlaybackState;
  calibrationPhase: 'calibrating' | 'calibration_complete' | 'playing' | 'paused';
  windowOffset: number;
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

  // Scale filter props (shown during playback, replay mode only)
  showScaleFilters?: boolean;
  displayConfig?: SwingDisplayConfig;
  onToggleScale?: (scale: SwingScaleKey) => void;

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
}

export const Sidebar: React.FC<SidebarProps> = ({
  mode,
  lingerEvents,
  onToggleLingerEvent,
  onResetDefaults,
  className = '',
  showScaleFilters = false,
  displayConfig,
  onToggleScale,
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
}) => {
  const scaleOrder: SwingScaleKey[] = ['XL', 'L', 'M', 'S'];
  const [feedbackText, setFeedbackText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitStatus, setSubmitStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [hasAutopaused, setHasAutopaused] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const handleFeedbackSubmit = useCallback(async () => {
    if (!feedbackText.trim() || currentPlaybackBar === undefined || !feedbackContext) return;

    setIsSubmitting(true);
    setSubmitStatus('idle');

    try {
      // Build rich context snapshot
      const snapshot: PlaybackFeedbackSnapshot = {
        state: feedbackContext.calibrationPhase,
        window_offset: feedbackContext.windowOffset,
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
          active_legs_count: dagContext.activeLegsCount,
          orphaned_origins_count: dagContext.orphanedOriginsCount,
          pending_pivots_count: dagContext.pendingPivotsCount,
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
  }, [feedbackText, lingerEvent, currentPlaybackBar, feedbackContext, mode, replayContext, dagContext, screenshotTargetRef]);

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

  const getIconForType = (type: string) => {
    switch (type) {
      case EventType.SWING_FORMED:
      case 'SWING_FORMED':
        return <Activity size={16} className="text-trading-purple" />;
      case EventType.COMPLETION:
      case 'SWING_COMPLETED':
        return <CheckCircle size={16} className="text-trading-bull" />;
      case EventType.INVALIDATION:
      case 'SWING_INVALIDATED':
        return <XCircle size={16} className="text-trading-bear" />;
      case EventType.LEVEL_CROSS:
      case 'LEVEL_CROSS':
        return <Eye size={16} className="text-trading-blue" />;
      case 'LEG_CREATED':
        return <GitBranch size={16} className="text-trading-blue" />;
      case 'LEG_PRUNED':
        return <Scissors size={16} className="text-trading-orange" />;
      case 'LEG_INVALIDATED':
        return <Ban size={16} className="text-trading-bear" />;
      default:
        return <AlertTriangle size={16} className="text-trading-orange" />;
    }
  };

  return (
    <aside className={`flex flex-col bg-app-secondary border-r border-app-border h-full ${className}`}>
      {/* Linger Event Toggles - only shown when linger is enabled */}
      {lingerEnabled && (
        <>
        {/* Sidebar Header */}
        <div className="p-4 border-b border-app-border">
          <h2 className="text-xs font-bold text-app-muted uppercase tracking-wider flex items-center gap-2">
            <Filter size={14} />
            {mode === 'dag' ? 'DAG Events' : 'Linger Events'}
          </h2>
        </div>

        {/* Event toggles */}
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
                {getIconForType(event.id)}
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
        </>
      )}

      {/* Scale Filters Section (shown during playback, replay mode only) */}
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

      {/* DAG Context Display (DAG mode only) */}
      {mode === 'dag' && dagContext && (
        <div className="p-4 border-t border-app-border">
          <h2 className="text-xs font-bold text-app-muted uppercase tracking-wider flex items-center gap-2 mb-3">
            <GitBranch size={14} />
            DAG State
          </h2>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-app-muted">Active Legs</span>
              <span className="text-app-text font-medium">{dagContext.activeLegsCount}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-app-muted">Orphaned Origins</span>
              <span className="text-app-text font-medium">
                <span className="text-trading-blue">{dagContext.orphanedOriginsCount.bull}</span>
                {' / '}
                <span className="text-trading-bear">{dagContext.orphanedOriginsCount.bear}</span>
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-app-muted">Pending Pivots</span>
              <span className="text-app-text font-medium">{dagContext.pendingPivotsCount}</span>
            </div>
          </div>
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
            {hasAutopaused && (
              <span className="flex items-center gap-1 text-trading-orange">
                <Pause size={10} />
                <span className="text-[10px] font-normal normal-case">paused</span>
              </span>
            )}
          </h2>
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
