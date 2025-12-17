import { useState, useRef, useCallback, useEffect } from 'react';
import { PlaybackState, DiscretizationEvent, FilterState, SwingData, DiscretizationSwing } from '../types';
import { LINGER_DURATION_MS } from '../constants';

interface UsePlaybackOptions {
  sourceBars: { timestamp: number }[];
  events: DiscretizationEvent[];
  swings: Record<string, DiscretizationSwing>;
  filters: FilterState[];
  playbackIntervalMs: number;
  onPositionChange?: (position: number) => void;
}

interface UsePlaybackReturn {
  playbackState: PlaybackState;
  currentPosition: number;
  isLingering: boolean;
  lingerTimeLeft: number;
  lingerEventType: string | undefined;
  lingerSwingId: string | undefined;
  lingerQueuePosition: { current: number; total: number } | undefined;
  currentSwing: SwingData | null;
  previousSwing: SwingData | null;
  play: () => void;
  pause: () => void;
  togglePlayPause: () => void;
  stepForward: () => void;
  stepBack: () => void;
  jumpToStart: () => void;
  jumpToEnd: () => void;
}

// Helper to convert event data to SwingData for the explanation panel
function eventToSwingData(event: DiscretizationEvent, swings: Record<string, DiscretizationSwing>): SwingData | null {
  if (event.event_type !== 'SWING_FORMED') return null;

  const explanation = event.data.explanation;
  if (!explanation) return null;

  const swing = swings[event.swing_id];
  if (!swing) return null;

  const isBull = swing.direction.toUpperCase() === 'BULL';
  const highPrice = isBull ? swing.anchor1 : swing.anchor0;
  const lowPrice = isBull ? swing.anchor0 : swing.anchor1;
  const highBar = isBull ? swing.anchor1_bar : swing.anchor0_bar;
  const lowBar = isBull ? swing.anchor0_bar : swing.anchor1_bar;

  return {
    id: event.swing_id,
    scale: swing.scale,
    direction: swing.direction,
    highPrice: explanation.high?.price ?? highPrice,
    highBar: explanation.high?.bar ?? highBar,
    highTime: explanation.high?.timestamp
      ? formatTimestamp(explanation.high.timestamp)
      : '',
    lowPrice: explanation.low?.price ?? lowPrice,
    lowBar: explanation.low?.bar ?? lowBar,
    lowTime: explanation.low?.timestamp
      ? formatTimestamp(explanation.low.timestamp)
      : '',
    size: explanation.size_pts ?? Math.abs(highPrice - lowPrice),
    sizePct: explanation.size_pct ?? 0,
    scaleReason: explanation.scale_reason,
    isAnchor: explanation.is_anchor,
    separation: explanation.separation ? {
      distanceFib: explanation.separation.distance_fib,
      minimumFib: explanation.separation.minimum_fib,
      fromSwingId: explanation.separation.from_swing_id,
    } : undefined,
    previousSwingId: explanation.separation?.from_swing_id,
  };
}

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return ts;
  }
}

export function usePlayback({
  sourceBars,
  events,
  swings,
  filters,
  playbackIntervalMs,
  onPositionChange,
}: UsePlaybackOptions): UsePlaybackReturn {
  const [playbackState, setPlaybackState] = useState<PlaybackState>(PlaybackState.STOPPED);
  const [currentPosition, setCurrentPosition] = useState(0);
  const [lingerTimeLeft, setLingerTimeLeft] = useState(0);
  const [lingerEventType, setLingerEventType] = useState<string | undefined>();
  const [lingerSwingId, setLingerSwingId] = useState<string | undefined>();
  const [lingerQueuePosition, setLingerQueuePosition] = useState<{ current: number; total: number } | undefined>();
  const [currentSwing, setCurrentSwing] = useState<SwingData | null>(null);
  const [previousSwing, setPreviousSwing] = useState<SwingData | null>(null);

  const playbackIntervalRef = useRef<number | null>(null);
  const lingerTimerRef = useRef<number | null>(null);
  const lingerStartRef = useRef<number | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const eventQueueRef = useRef<DiscretizationEvent[]>([]);
  const eventIndexRef = useRef(0);
  const advanceBarRef = useRef<() => void>(() => {});

  // Index events by bar for fast lookup
  const eventsByBar = useRef<Map<number, DiscretizationEvent[]>>(new Map());

  useEffect(() => {
    const indexed = new Map<number, DiscretizationEvent[]>();
    for (const event of events) {
      const existing = indexed.get(event.bar) || [];
      existing.push(event);
      indexed.set(event.bar, existing);
    }
    eventsByBar.current = indexed;
  }, [events]);

  // Get enabled events at a specific bar
  const getEnabledEventsAtBar = useCallback((bar: number): DiscretizationEvent[] => {
    const barEvents = eventsByBar.current.get(bar) || [];
    const enabledIds = new Set(filters.filter(f => f.isEnabled).map(f => f.id));
    return barEvents.filter(e => enabledIds.has(e.event_type));
  }, [filters]);

  // Clear all timers
  const clearTimers = useCallback(() => {
    if (playbackIntervalRef.current) {
      clearInterval(playbackIntervalRef.current);
      playbackIntervalRef.current = null;
    }
    if (lingerTimerRef.current) {
      clearTimeout(lingerTimerRef.current);
      lingerTimerRef.current = null;
    }
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
  }, []);

  // Update position and notify
  const updatePosition = useCallback((pos: number) => {
    setCurrentPosition(pos);
    onPositionChange?.(pos);
  }, [onPositionChange]);

  // Enter linger state
  const enterLinger = useCallback((eventsToShow: DiscretizationEvent[]) => {
    clearTimers();
    setPlaybackState(PlaybackState.LINGERING);
    eventQueueRef.current = eventsToShow;
    eventIndexRef.current = 0;

    const showCurrentEvent = () => {
      const event = eventQueueRef.current[eventIndexRef.current];
      if (!event) return;

      setLingerEventType(event.event_type);
      setLingerSwingId(event.swing_id);
      setLingerQueuePosition(
        eventQueueRef.current.length > 1
          ? { current: eventIndexRef.current + 1, total: eventQueueRef.current.length }
          : undefined
      );

      // Update swing explanation if SWING_FORMED
      if (event.event_type === 'SWING_FORMED') {
        const swingData = eventToSwingData(event, swings);
        if (swingData?.previousSwingId) {
          const prevSwing = swings[swingData.previousSwingId];
          if (prevSwing) {
            setPreviousSwing({
              id: swingData.previousSwingId,
              scale: prevSwing.scale,
              direction: prevSwing.direction,
              highPrice: prevSwing.direction === 'BULL' ? prevSwing.anchor1 : prevSwing.anchor0,
              lowPrice: prevSwing.direction === 'BULL' ? prevSwing.anchor0 : prevSwing.anchor1,
              highBar: prevSwing.direction === 'BULL' ? prevSwing.anchor1_bar : prevSwing.anchor0_bar,
              lowBar: prevSwing.direction === 'BULL' ? prevSwing.anchor0_bar : prevSwing.anchor1_bar,
              highTime: '',
              lowTime: '',
              size: 0,
              sizePct: 0,
            });
          }
        }
        setCurrentSwing(swingData);
      } else {
        setCurrentSwing(null);
        setPreviousSwing(null);
      }

      // Start linger timer
      lingerStartRef.current = Date.now();
      setLingerTimeLeft(LINGER_DURATION_MS / 1000);

      // Animate timer wheel
      const animateTimer = () => {
        if (lingerStartRef.current === null) return;
        const elapsed = Date.now() - lingerStartRef.current;
        const remaining = Math.max(0, (LINGER_DURATION_MS - elapsed) / 1000);
        setLingerTimeLeft(remaining);

        if (remaining > 0) {
          animationFrameRef.current = requestAnimationFrame(animateTimer);
        }
      };
      animationFrameRef.current = requestAnimationFrame(animateTimer);

      // Set auto-advance timer
      lingerTimerRef.current = window.setTimeout(() => {
        eventIndexRef.current++;
        if (eventIndexRef.current < eventQueueRef.current.length) {
          showCurrentEvent();
        } else {
          // Resume playback
          exitLinger();
          startPlayback();
        }
      }, LINGER_DURATION_MS);
    };

    showCurrentEvent();
  }, [clearTimers, swings]);

  // Exit linger state
  const exitLinger = useCallback(() => {
    clearTimers();
    eventQueueRef.current = [];
    eventIndexRef.current = 0;
    setLingerEventType(undefined);
    setLingerSwingId(undefined);
    setLingerQueuePosition(undefined);
    lingerStartRef.current = null;
    setLingerTimeLeft(0);
    setCurrentSwing(null);
    setPreviousSwing(null);
  }, [clearTimers]);

  // Advance one bar
  const advanceBar = useCallback(() => {
    if (currentPosition >= sourceBars.length - 1) {
      clearTimers();
      setPlaybackState(PlaybackState.STOPPED);
      return;
    }

    const newPos = currentPosition + 1;
    updatePosition(newPos);

    // Check for events at this bar
    const eventsAtBar = getEnabledEventsAtBar(newPos);
    if (eventsAtBar.length > 0) {
      enterLinger(eventsAtBar);
    }
  }, [currentPosition, sourceBars.length, updatePosition, getEnabledEventsAtBar, enterLinger, clearTimers]);

  // Keep advanceBarRef.current updated to avoid stale closures in setInterval
  useEffect(() => {
    advanceBarRef.current = advanceBar;
  }, [advanceBar]);

  // Start playback
  const startPlayback = useCallback(() => {
    if (playbackState === PlaybackState.LINGERING) {
      // Skip linger
      exitLinger();
    }

    if (currentPosition >= sourceBars.length - 1) {
      updatePosition(0);
    }

    setPlaybackState(PlaybackState.PLAYING);
    playbackIntervalRef.current = window.setInterval(() => {
      advanceBarRef.current();
    }, playbackIntervalMs);
  }, [playbackState, currentPosition, sourceBars.length, updatePosition, playbackIntervalMs, exitLinger]);

  // Pause playback
  const pause = useCallback(() => {
    clearTimers();
    setPlaybackState(PlaybackState.PAUSED);
  }, [clearTimers]);

  // Toggle play/pause
  const togglePlayPause = useCallback(() => {
    if (playbackState === PlaybackState.LINGERING) {
      exitLinger();
      startPlayback();
    } else if (playbackState === PlaybackState.PLAYING) {
      pause();
    } else {
      startPlayback();
    }
  }, [playbackState, startPlayback, pause, exitLinger]);

  // Step forward
  const stepForward = useCallback(() => {
    if (playbackState === PlaybackState.LINGERING) {
      exitLinger();
    }
    if (playbackState === PlaybackState.PLAYING) {
      clearTimers();
      setPlaybackState(PlaybackState.PAUSED);
    }
    if (currentPosition < sourceBars.length - 1) {
      updatePosition(currentPosition + 1);
    }
  }, [playbackState, currentPosition, sourceBars.length, updatePosition, clearTimers, exitLinger]);

  // Step back
  const stepBack = useCallback(() => {
    if (playbackState === PlaybackState.LINGERING) {
      exitLinger();
    }
    if (playbackState === PlaybackState.PLAYING) {
      clearTimers();
      setPlaybackState(PlaybackState.PAUSED);
    }
    if (currentPosition > 0) {
      updatePosition(currentPosition - 1);
    }
  }, [playbackState, currentPosition, updatePosition, clearTimers, exitLinger]);

  // Jump to start
  const jumpToStart = useCallback(() => {
    clearTimers();
    exitLinger();
    setPlaybackState(PlaybackState.STOPPED);
    updatePosition(0);
  }, [clearTimers, exitLinger, updatePosition]);

  // Jump to end
  const jumpToEnd = useCallback(() => {
    clearTimers();
    exitLinger();
    setPlaybackState(PlaybackState.STOPPED);
    if (sourceBars.length > 0) {
      updatePosition(sourceBars.length - 1);
    }
  }, [clearTimers, exitLinger, sourceBars.length, updatePosition]);

  // Restart interval when playbackIntervalMs changes during playback
  useEffect(() => {
    if (playbackState === PlaybackState.PLAYING && playbackIntervalRef.current) {
      clearInterval(playbackIntervalRef.current);
      playbackIntervalRef.current = window.setInterval(() => {
        advanceBarRef.current();
      }, playbackIntervalMs);
    }
  }, [playbackIntervalMs, playbackState]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTimers();
    };
  }, [clearTimers]);

  return {
    playbackState,
    currentPosition,
    isLingering: playbackState === PlaybackState.LINGERING,
    lingerTimeLeft,
    lingerEventType,
    lingerSwingId,
    lingerQueuePosition,
    currentSwing,
    previousSwing,
    play: startPlayback,
    pause,
    togglePlayPause,
    stepForward,
    stepBack,
    jumpToStart,
    jumpToEnd,
  };
}
