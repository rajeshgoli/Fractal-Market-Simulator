import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { PlaybackState, BarData, FilterState, SwingScaleKey } from '../types';
import { advanceReplay, ReplayEvent, ReplaySwingState } from '../lib/api';
import { LINGER_DURATION_MS } from '../constants';

interface UseForwardPlaybackOptions {
  calibrationBarCount: number;
  calibrationBars: BarData[];
  playbackIntervalMs: number;
  filters: FilterState[];  // Event type filters
  enabledScales: Set<SwingScaleKey>;  // Scale filters
  onNewBars?: (bars: BarData[]) => void;
  onSwingStateChange?: (state: ReplaySwingState) => void;
  onRefreshAggregatedBars?: () => void;  // Called after advance to refresh chart bars
}

interface UseForwardPlaybackReturn {
  playbackState: PlaybackState;
  currentPosition: number;
  visibleBars: BarData[];
  isLingering: boolean;
  lingerTimeLeft: number;
  lingerEvent: ReplayEvent | undefined;
  lingerSwingId: string | undefined;
  lingerQueuePosition: { current: number; total: number } | undefined;
  currentSwingState: ReplaySwingState | null;
  endOfData: boolean;
  // Event navigation
  allEvents: ReplayEvent[];
  currentEventIndex: number;  // 0-based index of current event, -1 if before first event
  hasPreviousEvent: boolean;
  hasNextEvent: boolean;
  // Controls
  play: () => void;
  pause: () => void;
  togglePlayPause: () => void;
  stepForward: () => void;
  stepBack: () => void;
  jumpToStart: () => void;
  jumpToPreviousEvent: () => void;
  jumpToNextEvent: () => void;
  navigatePrevEvent: () => void;
  navigateNextEvent: () => void;
  dismissLinger: () => void;
}

export function useForwardPlayback({
  calibrationBarCount,
  calibrationBars,
  playbackIntervalMs,
  filters,
  enabledScales,
  onNewBars,
  onSwingStateChange,
  onRefreshAggregatedBars,
}: UseForwardPlaybackOptions): UseForwardPlaybackReturn {
  // Playback state
  const [playbackState, setPlaybackState] = useState<PlaybackState>(PlaybackState.STOPPED);
  const [currentPosition, setCurrentPosition] = useState(calibrationBarCount - 1);
  const [visibleBars, setVisibleBars] = useState<BarData[]>(calibrationBars);
  const [endOfData, setEndOfData] = useState(false);

  // Linger state
  const [lingerTimeLeft, setLingerTimeLeft] = useState(0);
  const [lingerEvent, setLingerEvent] = useState<ReplayEvent | undefined>();
  const [lingerSwingId, setLingerSwingId] = useState<string | undefined>();
  const [lingerQueuePosition, setLingerQueuePosition] = useState<{ current: number; total: number } | undefined>();

  // Swing state
  const [currentSwingState, setCurrentSwingState] = useState<ReplaySwingState | null>(null);

  // Event tracking for navigation
  const [allEvents, setAllEvents] = useState<ReplayEvent[]>([]);

  // Refs for timers and queue
  const playbackIntervalRef = useRef<number | null>(null);
  const lingerTimerRef = useRef<number | null>(null);
  const lingerStartRef = useRef<number | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const eventQueueRef = useRef<ReplayEvent[]>([]);
  const eventIndexRef = useRef(0);
  const advancePendingRef = useRef(false);
  const isPlayingRef = useRef(false); // Ref to avoid stale closures in setTimeout chain

  // Ref to hold the latest functions (avoids stale closures)
  const showCurrentEventRef = useRef<() => void>(() => {});
  const exitLingerRef = useRef<() => void>(() => {});
  const startPlaybackRef = useRef<() => void>(() => {});

  // Initialize visible bars from calibration
  useEffect(() => {
    setVisibleBars(calibrationBars);
    setCurrentPosition(calibrationBarCount - 1);
  }, [calibrationBars, calibrationBarCount]);

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

  // Show the current event in the queue
  const showCurrentEvent = useCallback(() => {
    const event = eventQueueRef.current[eventIndexRef.current];
    if (!event) return;

    setLingerEvent(event);
    setLingerSwingId(event.swing_id);
    setLingerQueuePosition(
      eventQueueRef.current.length > 1
        ? { current: eventIndexRef.current + 1, total: eventQueueRef.current.length }
        : undefined
    );

    // Clear existing timers
    if (lingerTimerRef.current) {
      clearTimeout(lingerTimerRef.current);
      lingerTimerRef.current = null;
    }
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
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
        showCurrentEventRef.current();
      } else {
        // Resume playback
        exitLingerRef.current();
        startPlaybackRef.current();
      }
    }, LINGER_DURATION_MS);
  }, []);

  // Keep showCurrentEventRef updated
  useEffect(() => {
    showCurrentEventRef.current = showCurrentEvent;
  }, [showCurrentEvent]);

  // Exit linger state
  const exitLinger = useCallback(() => {
    clearTimers();
    eventQueueRef.current = [];
    eventIndexRef.current = 0;
    setLingerEvent(undefined);
    setLingerSwingId(undefined);
    setLingerQueuePosition(undefined);
    lingerStartRef.current = null;
    setLingerTimeLeft(0);
  }, [clearTimers]);

  // Keep exitLingerRef updated
  useEffect(() => {
    exitLingerRef.current = exitLinger;
  }, [exitLinger]);

  // Enter linger state with events
  const enterLinger = useCallback((events: ReplayEvent[]) => {
    isPlayingRef.current = false;
    clearTimers();
    setPlaybackState(PlaybackState.LINGERING);
    eventQueueRef.current = events;
    eventIndexRef.current = 0;
    showCurrentEventRef.current();
  }, [clearTimers]);

  // Filter events based on event type and scale filters
  const filterEvents = useCallback((events: ReplayEvent[]): ReplayEvent[] => {
    // Get enabled event types from filters
    const enabledEventTypes = new Set(
      filters.filter(f => f.isEnabled).map(f => f.id)
    );

    return events.filter(event => {
      // Check event type filter
      // Map backend event types to frontend types
      let eventType = event.type;
      if (eventType === 'SWING_INVALIDATED') eventType = 'INVALIDATION' as typeof event.type;
      if (eventType === 'SWING_COMPLETED') eventType = 'COMPLETION' as typeof event.type;

      if (!enabledEventTypes.has(eventType)) {
        return false;
      }

      // Check scale filter
      const eventScale = event.scale as SwingScaleKey;
      if (!enabledScales.has(eventScale)) {
        return false;
      }

      return true;
    });
  }, [filters, enabledScales]);

  // Advance one bar (call API)
  const advanceBar = useCallback(async () => {
    if (endOfData || advancePendingRef.current) return;

    advancePendingRef.current = true;
    try {
      const response = await advanceReplay(calibrationBarCount, currentPosition, 1);

      // Update end of data
      if (response.end_of_data) {
        setEndOfData(true);
        clearTimers();
        setPlaybackState(PlaybackState.STOPPED);
        advancePendingRef.current = false;
        return;
      }

      // Append new bars
      if (response.new_bars.length > 0) {
        const newBarData: BarData[] = response.new_bars.map(bar => ({
          index: bar.index,
          timestamp: bar.timestamp,
          open: bar.open,
          high: bar.high,
          low: bar.low,
          close: bar.close,
          source_start_index: bar.index,
          source_end_index: bar.index,
        }));

        setVisibleBars(prev => [...prev, ...newBarData]);
        setCurrentPosition(response.current_bar_index);
        onNewBars?.(newBarData);

        // Signal parent to refresh aggregated bars (backend now controls visibility)
        onRefreshAggregatedBars?.();
      }

      // Update swing state
      setCurrentSwingState(response.swing_state);
      onSwingStateChange?.(response.swing_state);

      // Accumulate all events for navigation history (unfiltered)
      if (response.events.length > 0) {
        setAllEvents(prev => [...prev, ...response.events]);
      }

      // Filter events for linger based on event type and scale filters
      const filteredEvents = filterEvents(response.events);
      if (filteredEvents.length > 0) {
        // Trigger linger only for filtered events
        enterLinger(filteredEvents);
      }
    } catch (err) {
      console.error('Failed to advance replay:', err);
      clearTimers();
      setPlaybackState(PlaybackState.PAUSED);
    } finally {
      advancePendingRef.current = false;
    }
  }, [calibrationBarCount, currentPosition, endOfData, clearTimers, enterLinger, filterEvents, onNewBars, onSwingStateChange, onRefreshAggregatedBars]);

  // Ref to hold the latest advanceBar function
  const advanceBarRef = useRef<() => Promise<void>>(async () => {});

  // Keep advanceBarRef updated
  useEffect(() => {
    advanceBarRef.current = advanceBar;
  }, [advanceBar]);

  // Start playback
  const startPlayback = useCallback(() => {
    if (playbackState === PlaybackState.LINGERING) {
      exitLinger();
    }

    if (endOfData) {
      return;
    }

    isPlayingRef.current = true;
    setPlaybackState(PlaybackState.PLAYING);

    // Use setTimeout chain instead of setInterval for async operations
    const scheduleNext = () => {
      if (!isPlayingRef.current) return;

      playbackIntervalRef.current = window.setTimeout(async () => {
        if (!isPlayingRef.current) return;
        await advanceBarRef.current();
        // Only schedule next if still playing (not in linger)
        if (isPlayingRef.current && !advancePendingRef.current) {
          scheduleNext();
        }
      }, playbackIntervalMs);
    };

    scheduleNext();
  }, [playbackState, endOfData, playbackIntervalMs, exitLinger]);

  // Keep startPlaybackRef updated
  useEffect(() => {
    startPlaybackRef.current = startPlayback;
  }, [startPlayback]);

  // Pause playback
  const pause = useCallback(() => {
    isPlayingRef.current = false;
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

  // Step forward (single bar)
  const stepForward = useCallback(async () => {
    if (playbackState === PlaybackState.LINGERING) {
      exitLinger();
    }
    if (playbackState === PlaybackState.PLAYING) {
      isPlayingRef.current = false;
      clearTimers();
    }
    setPlaybackState(PlaybackState.PAUSED);
    await advanceBar();
  }, [playbackState, clearTimers, exitLinger, advanceBar]);

  // Step back (not supported in forward-only mode - just pause)
  const stepBack = useCallback(() => {
    if (playbackState === PlaybackState.LINGERING) {
      exitLinger();
    }
    if (playbackState === PlaybackState.PLAYING) {
      isPlayingRef.current = false;
      clearTimers();
    }
    setPlaybackState(PlaybackState.PAUSED);
    // Note: Cannot actually go back in forward-only mode
  }, [playbackState, clearTimers, exitLinger]);

  // Jump to start (reset to calibration end)
  const jumpToStart = useCallback(() => {
    isPlayingRef.current = false;
    clearTimers();
    exitLinger();
    setPlaybackState(PlaybackState.STOPPED);
    setVisibleBars(calibrationBars);
    setCurrentPosition(calibrationBarCount - 1);
    setEndOfData(false);
    setCurrentSwingState(null);
    setAllEvents([]); // Reset events when resetting to start
  }, [clearTimers, exitLinger, calibrationBars, calibrationBarCount]);

  // Navigate to previous event in linger queue
  const navigatePrevEvent = useCallback(() => {
    if (playbackState !== PlaybackState.LINGERING) return;
    if (eventIndexRef.current <= 0) return;

    eventIndexRef.current--;
    showCurrentEventRef.current();
  }, [playbackState]);

  // Navigate to next event in linger queue
  const navigateNextEvent = useCallback(() => {
    if (playbackState !== PlaybackState.LINGERING) return;
    if (eventIndexRef.current >= eventQueueRef.current.length - 1) return;

    eventIndexRef.current++;
    showCurrentEventRef.current();
  }, [playbackState]);

  // Dismiss linger and resume playback
  const dismissLinger = useCallback(() => {
    if (playbackState !== PlaybackState.LINGERING) return;
    exitLinger();
    startPlayback();
  }, [playbackState, exitLinger, startPlayback]);

  // Compute current event index (index of last event at or before current position)
  const currentEventIndex = useMemo(() => {
    if (allEvents.length === 0) return -1;
    // Find the last event at or before currentPosition
    for (let i = allEvents.length - 1; i >= 0; i--) {
      if (allEvents[i].bar_index <= currentPosition) {
        return i;
      }
    }
    return -1;
  }, [allEvents, currentPosition]);

  // Check if there are events before current position
  const hasPreviousEvent = useMemo(() => {
    if (allEvents.length === 0) return false;
    // Find events before the current event
    if (currentEventIndex <= 0) {
      // If at first event or before any event, check if there's any event at a previous bar
      const currentEventBar = currentEventIndex >= 0 ? allEvents[currentEventIndex].bar_index : currentPosition;
      return allEvents.some(e => e.bar_index < currentEventBar);
    }
    return true;
  }, [allEvents, currentEventIndex, currentPosition]);

  // Check if there could be more events (not at end of data)
  const hasNextEvent = !endOfData;

  // Jump to previous event
  const jumpToPreviousEvent = useCallback(async () => {
    if (allEvents.length === 0) return;

    // Exit linger if active
    if (playbackState === PlaybackState.LINGERING) {
      exitLinger();
    }
    if (playbackState === PlaybackState.PLAYING) {
      isPlayingRef.current = false;
      clearTimers();
    }
    setPlaybackState(PlaybackState.PAUSED);

    // Find the bar index of the previous event
    let targetBarIndex: number | null = null;

    if (currentEventIndex >= 0) {
      // Current position is at or after an event
      const currentEventBar = allEvents[currentEventIndex].bar_index;

      if (currentPosition > currentEventBar) {
        // We're past the current event's bar, jump to it
        targetBarIndex = currentEventBar;
      } else if (currentEventIndex > 0) {
        // We're at the current event's bar, jump to previous event
        targetBarIndex = allEvents[currentEventIndex - 1].bar_index;
      }
    }

    if (targetBarIndex !== null && targetBarIndex >= 0) {
      // Reset visible bars to show bars up to target
      // We need to recalculate how many bars from calibration
      const newVisibleBars = calibrationBars.slice(0, Math.min(targetBarIndex + 1, calibrationBars.length));
      setVisibleBars(newVisibleBars);
      setCurrentPosition(targetBarIndex);

      // Find events at this bar for linger display (filtered)
      const eventsAtBar = allEvents.filter(e => e.bar_index === targetBarIndex);
      const filteredEventsAtBar = filterEvents(eventsAtBar);
      if (filteredEventsAtBar.length > 0) {
        enterLinger(filteredEventsAtBar);
      }
    }
  }, [allEvents, currentEventIndex, currentPosition, playbackState, exitLinger, clearTimers, calibrationBars, enterLinger, filterEvents]);

  // Jump to next event (advance until an event occurs)
  const jumpToNextEvent = useCallback(async () => {
    if (endOfData) return;

    // Exit linger if active
    if (playbackState === PlaybackState.LINGERING) {
      exitLinger();
    }
    if (playbackState === PlaybackState.PLAYING) {
      isPlayingRef.current = false;
      clearTimers();
    }
    setPlaybackState(PlaybackState.PAUSED);

    // Advance bars until we hit an event or end of data
    let foundEvent = false;
    let iterations = 0;
    const maxIterations = 1000; // Safety limit

    while (!foundEvent && iterations < maxIterations) {
      iterations++;
      advancePendingRef.current = true;

      try {
        const response = await advanceReplay(calibrationBarCount, currentPosition + iterations - 1, 1);

        if (response.end_of_data) {
          setEndOfData(true);
          // Still update position to show we reached the end
          if (response.new_bars.length > 0) {
            const newBarData: BarData[] = response.new_bars.map(bar => ({
              index: bar.index,
              timestamp: bar.timestamp,
              open: bar.open,
              high: bar.high,
              low: bar.low,
              close: bar.close,
              source_start_index: bar.index,
              source_end_index: bar.index,
            }));
            setVisibleBars(prev => [...prev, ...newBarData]);
            setCurrentPosition(response.current_bar_index);
            onNewBars?.(newBarData);
            onRefreshAggregatedBars?.();
          }
          break;
        }

        // Append new bars
        if (response.new_bars.length > 0) {
          const newBarData: BarData[] = response.new_bars.map(bar => ({
            index: bar.index,
            timestamp: bar.timestamp,
            open: bar.open,
            high: bar.high,
            low: bar.low,
            close: bar.close,
            source_start_index: bar.index,
            source_end_index: bar.index,
          }));
          setVisibleBars(prev => [...prev, ...newBarData]);
          setCurrentPosition(response.current_bar_index);
          onNewBars?.(newBarData);
          onRefreshAggregatedBars?.();
        }

        // Update swing state
        setCurrentSwingState(response.swing_state);
        onSwingStateChange?.(response.swing_state);

        // Accumulate all events for navigation history
        if (response.events.length > 0) {
          setAllEvents(prev => [...prev, ...response.events]);
        }

        // Check for filtered events (only linger on events matching filters)
        const filteredEvents = filterEvents(response.events);
        if (filteredEvents.length > 0) {
          enterLinger(filteredEvents);
          foundEvent = true;
        }
      } catch (err) {
        console.error('Failed to advance replay:', err);
        break;
      }
    }

    advancePendingRef.current = false;
  }, [endOfData, playbackState, exitLinger, clearTimers, calibrationBarCount, currentPosition, enterLinger, filterEvents, onNewBars, onSwingStateChange, onRefreshAggregatedBars]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTimers();
    };
  }, [clearTimers]);

  return {
    playbackState,
    currentPosition,
    visibleBars,
    isLingering: playbackState === PlaybackState.LINGERING,
    lingerTimeLeft,
    lingerEvent,
    lingerSwingId,
    lingerQueuePosition,
    currentSwingState,
    endOfData,
    // Event navigation
    allEvents,
    currentEventIndex,
    hasPreviousEvent,
    hasNextEvent,
    // Controls
    play: startPlayback,
    pause,
    togglePlayPause,
    stepForward,
    stepBack,
    jumpToStart,
    jumpToPreviousEvent,
    jumpToNextEvent,
    navigatePrevEvent,
    navigateNextEvent,
    dismissLinger,
  };
}
