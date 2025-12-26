import React, { useState, useCallback, useRef, RefObject } from 'react';
import { toPng } from 'html-to-image';
import { PlaybackState, DetectionConfig } from '../types';
import { MessageSquare, Send, Pause, Paperclip, X } from 'lucide-react';
import { submitPlaybackFeedback, PlaybackFeedbackEventContext, PlaybackFeedbackSnapshot, ReplayEvent, DagLeg } from '../lib/api';
import { AttachableItem } from './DAGStatePanel';
import { LifecycleEventWithLegInfo } from '../hooks/useFollowLeg';

// Feedback context passed from parent
export interface FeedbackContext {
  playbackState: PlaybackState;
  calibrationPhase: 'calibrating' | 'calibration_complete' | 'playing' | 'paused';
  csvIndex: number;
  calibrationBarCount: number;
  currentBarIndex: number;
  swingsFoundByScale: {
    XL: number;
    L: number;
    M: number;
    S: number;
  };
  totalEvents: number;
  swingsInvalidated: number;
  swingsCompleted: number;
}

// Replay mode context
export interface ReplayContext {
  selectedSwing?: {
    id: string;
    scale: string;
    direction: string;
  };
  calibrationState: 'calibrating' | 'calibration_complete' | 'playing' | 'paused';
}

// DAG mode context
export interface DagContextLeg {
  leg_id: string;
  direction: 'bull' | 'bear';
  pivot_price: number;
  pivot_index: number;
  origin_price: number;
  origin_index: number;
  range: number;
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

interface FeedbackFormProps {
  mode: 'replay' | 'dag';
  isLingering: boolean;
  lingerEvent?: ReplayEvent;
  currentPlaybackBar: number;
  feedbackContext: FeedbackContext;
  onFeedbackFocus?: () => void;
  onFeedbackBlur?: () => void;
  onPausePlayback?: () => void;
  replayContext?: ReplayContext;
  dagContext?: DagContext;
  screenshotTargetRef?: RefObject<HTMLElement | null>;
  attachedItems: AttachableItem[];
  onDetachItem: (item: AttachableItem) => void;
  onClearAttachments: () => void;
  detectionConfig?: DetectionConfig;
}

export const FeedbackForm: React.FC<FeedbackFormProps> = ({
  mode,
  isLingering,
  lingerEvent,
  currentPlaybackBar,
  feedbackContext,
  onFeedbackFocus,
  onFeedbackBlur,
  onPausePlayback,
  replayContext,
  dagContext,
  screenshotTargetRef,
  attachedItems,
  onDetachItem,
  onClearAttachments,
  detectionConfig,
}) => {
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
      const snapshot: PlaybackFeedbackSnapshot = {
        state: feedbackContext.calibrationPhase,
        csv_index: feedbackContext.csvIndex,
        bars_since_calibration: feedbackContext.currentBarIndex - feedbackContext.calibrationBarCount,
        current_bar_index: feedbackContext.currentBarIndex,
        calibration_bar_count: feedbackContext.calibrationBarCount,
        swings_found: feedbackContext.swingsFoundByScale,
        swings_invalidated: feedbackContext.swingsInvalidated,
        swings_completed: feedbackContext.swingsCompleted,
        mode,
      };

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
        };
      }

      let screenshotData: string | undefined;
      if (screenshotTargetRef?.current) {
        try {
          const dataUrl = await toPng(screenshotTargetRef.current, {
            backgroundColor: '#1a1a2e',
            pixelRatio: 1,
          });
          screenshotData = dataUrl.split(',')[1];
        } catch (err) {
          console.warn('Failed to capture screenshot:', err);
        }
      }

      await submitPlaybackFeedback(feedbackText, currentPlaybackBar, snapshot, screenshotData);
      setFeedbackText('');
      onClearAttachments();
      setSubmitStatus('success');
      setHasAutopaused(false);
      setTimeout(() => setSubmitStatus('idle'), 2000);
    } catch (err) {
      console.error('Failed to submit feedback:', err);
      setSubmitStatus('error');
      setTimeout(() => setSubmitStatus('idle'), 3000);
    } finally {
      setIsSubmitting(false);
    }
  }, [feedbackText, lingerEvent, currentPlaybackBar, feedbackContext, mode, replayContext, dagContext, screenshotTargetRef, attachedItems, onClearAttachments, detectionConfig]);

  const handleInputFocus = useCallback(() => {
    onFeedbackFocus?.();
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
    if (!hasAutopaused && !isLingering && feedbackContext?.playbackState === PlaybackState.PLAYING) {
      onPausePlayback?.();
      setHasAutopaused(true);
    }
  }, [hasAutopaused, isLingering, feedbackContext?.playbackState, onPausePlayback]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleFeedbackSubmit();
    }
  }, [handleFeedbackSubmit]);

  return (
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
  );
};
