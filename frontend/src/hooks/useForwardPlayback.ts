import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { PlaybackState, BarData, FilterState } from '../types';
import { advanceReplay, ReplayEvent, ReplaySwingState, AggregatedBarsResponse, DagStateResponse } from '../lib/api';
import { LINGER_DURATION_MS } from '../constants';

// Default history buffer size (configurable)
const DEFAULT_HISTORY_BUFFER_SIZE = 100;

// Snapshot of state at a given position for backward navigation
interface HistorySnapshot {
  barIndex: number;
  visibleBars: BarData[];
  dagState: DagStateResponse | null;
  aggregatedBars: AggregatedBarsResponse | null;
  swingState: ReplaySwingState | null;
  allEvents: ReplayEvent[];
}

interface UseForwardPlaybackOptions {
  calibrationBarCount: number;
  calibrationBars: BarData[];
  playbackIntervalMs: number;
  barsPerAdvance: number;  // How many source bars to advance per tick (aggregation factor)
  filters: FilterState[];  // Event type filters
  lingerEnabled?: boolean;  // Whether to pause on events (default: true)
  chartAggregationScales?: string[];  // Scales to include in response (e.g., ["S", "M"])
  includeDagState?: boolean;  // Whether to include DAG state in response
  historyBufferSize?: number;  // Max positions to cache for step back (default: 100)
  onNewBars?: (bars: BarData[]) => void;
  onSwingStateChange?: (state: ReplaySwingState) => void;
  onAggregatedBarsChange?: (bars: AggregatedBarsResponse) => void;  // Called with aggregated bars
  onDagStateChange?: (state: DagStateResponse) => void;  // Called with DAG state
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
  // Backward navigation
  canStepBack: boolean;  // Whether step back is available (has cached history)
  historySize: number;   // Current number of cached positions
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
  // Timer pause (for feedback input)
  pauseLingerTimer: () => void;
  resumeLingerTimer: () => void;
}

export function useForwardPlayback({
  calibrationBarCount,
  calibrationBars,
  playbackIntervalMs,
  barsPerAdvance,
  filters,
  lingerEnabled = true,
  chartAggregationScales,
  includeDagState = false,
  historyBufferSize = DEFAULT_HISTORY_BUFFER_SIZE,
  onNewBars,
  onSwingStateChange,
  onAggregatedBarsChange,
  onDagStateChange,
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

  // History buffer for backward navigation (#278)
  const historyBufferRef = useRef<HistorySnapshot[]>([]);
  const [historySize, setHistorySize] = useState(0);
  // Track current position in history for forward/backward navigation
  const historyIndexRef = useRef(-1);  // -1 means at latest, >=0 means viewing cached history
  // Store latest DAG state and aggregated bars for snapshotting
  const latestDagStateRef = useRef<DagStateResponse | null>(null);
  const latestAggregatedBarsRef = useRef<AggregatedBarsResponse | null>(null);

  // Refs for timers and queue
  const playbackIntervalRef = useRef<number | null>(null);
  const lingerTimerRef = useRef<number | null>(null);
  const lingerStartRef = useRef<number | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const eventQueueRef = useRef<ReplayEvent[]>([]);
  const eventIndexRef = useRef(0);
  const advancePendingRef = useRef(false);
  const isPlayingRef = useRef(false); // Ref to avoid stale closures in setTimeout chain
  const lingerPausedRef = useRef(false); // Whether linger timer is paused (for feedback input)
  const lingerRemainingRef = useRef(0); // Remaining time when paused
  const wasPlayingBeforeLingerRef = useRef(false); // Track if playback was active before linger

  // Bar buffer for smooth animation (batched fetch, individual render)
  interface BufferedBar {
    bar: BarData;
    events: ReplayEvent[];
  }
  const barBufferRef = useRef<BufferedBar[]>([]);
  const lastFetchedPositionRef = useRef(calibrationBarCount - 1);
  const isFetchingRef = useRef(false);
  const pendingAggregatedBarsRef = useRef<import('../lib/api').AggregatedBarsResponse | null>(null);
  const pendingDagStateRef = useRef<import('../lib/api').DagStateResponse | null>(null);
  const pendingSwingStateRef = useRef<ReplaySwingState | null>(null);

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

  // Push a snapshot to the history buffer (#278)
  const pushHistorySnapshot = useCallback((
    barIndex: number,
    bars: BarData[],
    events: ReplayEvent[],
    dagState: DagStateResponse | null,
    aggregatedBars: AggregatedBarsResponse | null,
    swingState: ReplaySwingState | null
  ) => {
    const snapshot: HistorySnapshot = {
      barIndex,
      visibleBars: [...bars],  // Clone to avoid reference issues
      dagState,
      aggregatedBars,
      swingState,
      allEvents: [...events],
    };

    // If we're viewing history (stepped back), truncate future when advancing
    if (historyIndexRef.current >= 0) {
      historyBufferRef.current = historyBufferRef.current.slice(0, historyIndexRef.current + 1);
      historyIndexRef.current = -1;  // Back to latest
    }

    historyBufferRef.current.push(snapshot);

    // Trim buffer if it exceeds max size
    if (historyBufferRef.current.length > historyBufferSize) {
      historyBufferRef.current.shift();
    }

    setHistorySize(historyBufferRef.current.length);
  }, [historyBufferSize]);

  // Restore state from a history snapshot (#278)
  const restoreFromSnapshot = useCallback((snapshot: HistorySnapshot) => {
    setVisibleBars(snapshot.visibleBars);
    setCurrentPosition(snapshot.barIndex);
    setAllEvents(snapshot.allEvents);
    setCurrentSwingState(snapshot.swingState);

    // Update DAG state via callback
    if (snapshot.dagState && onDagStateChange) {
      onDagStateChange(snapshot.dagState);
    }

    // Update aggregated bars via callback
    if (snapshot.aggregatedBars && onAggregatedBarsChange) {
      onAggregatedBarsChange(snapshot.aggregatedBars);
    }

    // Update swing state via callback
    if (snapshot.swingState && onSwingStateChange) {
      onSwingStateChange(snapshot.swingState);
    }
  }, [onDagStateChange, onAggregatedBarsChange, onSwingStateChange]);

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
        // Only resume playback if it was playing before linger
        exitLingerRef.current();
        if (wasPlayingBeforeLingerRef.current) {
          startPlaybackRef.current();
        }
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
  const enterLinger = useCallback((events: ReplayEvent[], wasPlaying: boolean = false) => {
    wasPlayingBeforeLingerRef.current = wasPlaying;
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

      return true;
    });
  }, [filters]);

  // Fetch a batch of bars into the buffer (background fetch)
  const fetchBatch = useCallback(async () => {
    if (endOfData || isFetchingRef.current) {
      return;
    }

    isFetchingRef.current = true;
    try {
      // Fetch from the last fetched position
      const response = await advanceReplay(
        calibrationBarCount,
        lastFetchedPositionRef.current,
        barsPerAdvance,
        chartAggregationScales,
        includeDagState
      );

      // Convert bars to buffered format with per-bar events
      if (response.new_bars.length > 0) {
        // Group events by bar index
        const eventsByBar: Map<number, ReplayEvent[]> = new Map();
        for (const event of response.events) {
          const existing = eventsByBar.get(event.bar_index) || [];
          existing.push(event);
          eventsByBar.set(event.bar_index, existing);
        }

        // Add bars to buffer
        const newBufferedBars: typeof barBufferRef.current = response.new_bars.map(bar => ({
          bar: {
            index: bar.index,
            timestamp: bar.timestamp,
            open: bar.open,
            high: bar.high,
            low: bar.low,
            close: bar.close,
            source_start_index: bar.index,
            source_end_index: bar.index,
          },
          events: eventsByBar.get(bar.index) || [],
        }));

        barBufferRef.current = [...barBufferRef.current, ...newBufferedBars];
        lastFetchedPositionRef.current = response.current_bar_index;

        // Store aggregated bars and DAG state to apply when buffer is consumed
        if (response.aggregated_bars) {
          pendingAggregatedBarsRef.current = response.aggregated_bars;
        }
        if (response.dag_state) {
          pendingDagStateRef.current = response.dag_state;
        }
        pendingSwingStateRef.current = response.swing_state;

        // Accumulate events for navigation
        if (response.events.length > 0) {
          setAllEvents(prev => [...prev, ...response.events]);
        }
      }

      if (response.end_of_data) {
        setEndOfData(true);
      }
    } catch (err) {
      console.error('Failed to fetch batch:', err);
    } finally {
      isFetchingRef.current = false;
    }
  }, [calibrationBarCount, barsPerAdvance, chartAggregationScales, includeDagState, endOfData]);

  // Render one bar from the buffer (called by animation timer)
  const renderNextBar = useCallback(() => {
    const buffer = barBufferRef.current;

    // Check if buffer is empty
    if (buffer.length === 0) {
      if (endOfData) {
        isPlayingRef.current = false;
        clearTimers();
        setPlaybackState(PlaybackState.STOPPED);
      }
      return false; // Nothing to render
    }

    // Pop first bar from buffer
    const { bar, events } = buffer.shift()!;

    // Render the bar - use functional update to get latest state for snapshot
    let newVisibleBars: BarData[] = [];
    let newAllEvents: ReplayEvent[] = [];
    setVisibleBars(prev => {
      newVisibleBars = [...prev, bar];
      return newVisibleBars;
    });
    setCurrentPosition(bar.index);
    onNewBars?.([bar]);

    // Apply pending aggregated bars and DAG state (only on last bar of batch or every bar)
    if (pendingAggregatedBarsRef.current && onAggregatedBarsChange) {
      onAggregatedBarsChange(pendingAggregatedBarsRef.current);
      latestAggregatedBarsRef.current = pendingAggregatedBarsRef.current;
    }
    if (pendingDagStateRef.current && onDagStateChange) {
      onDagStateChange(pendingDagStateRef.current);
      latestDagStateRef.current = pendingDagStateRef.current;
    }
    if (pendingSwingStateRef.current) {
      setCurrentSwingState(pendingSwingStateRef.current);
      onSwingStateChange?.(pendingSwingStateRef.current);
    }

    // Accumulate events for history snapshot
    setAllEvents(prev => {
      newAllEvents = events.length > 0 ? [...prev, ...events] : prev;
      return newAllEvents;
    });

    // Push snapshot to history buffer for backward navigation (#278)
    // Use setTimeout to ensure state updates have been applied
    setTimeout(() => {
      pushHistorySnapshot(
        bar.index,
        newVisibleBars,
        newAllEvents,
        latestDagStateRef.current,
        latestAggregatedBarsRef.current,
        pendingSwingStateRef.current
      );
    }, 0);

    // Check for events that should trigger linger
    const filteredEvents = filterEvents(events);
    if (filteredEvents.length > 0 && lingerEnabled) {
      enterLinger(filteredEvents, true);
      return true; // Bar rendered, but entering linger
    }

    // Trigger background fetch if buffer is running low (less than half full)
    if (buffer.length < barsPerAdvance / 2 && !isFetchingRef.current && !endOfData) {
      fetchBatch();
    }

    return true; // Bar rendered successfully
  }, [endOfData, clearTimers, filterEvents, lingerEnabled, enterLinger, barsPerAdvance, fetchBatch, onNewBars, onAggregatedBarsChange, onDagStateChange, onSwingStateChange, pushHistorySnapshot]);

  // Legacy advanceBar - still used for stepForward and jumpToNextEvent
  const advanceBar = useCallback(async () => {
    if (endOfData || advancePendingRef.current) {
      return;
    }

    advancePendingRef.current = true;
    try {
      // Request aggregated bars and DAG state in the same API call
      // Use barsPerAdvance to step by speed aggregation unit (e.g., 12 5m bars for 1H speed)
      const response = await advanceReplay(
        calibrationBarCount,
        currentPosition,
        barsPerAdvance,
        chartAggregationScales,
        includeDagState
      );

      // Append new bars (process even if end_of_data to update UI correctly)
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

        // Update lastFetchedPosition to stay in sync
        lastFetchedPositionRef.current = response.current_bar_index;
      }

      // Update aggregated bars from response (replaces separate API call)
      if (response.aggregated_bars && onAggregatedBarsChange) {
        onAggregatedBarsChange(response.aggregated_bars);
      }

      // Update DAG state from response (replaces separate API call)
      if (response.dag_state && onDagStateChange) {
        onDagStateChange(response.dag_state);
      }

      // Update swing state
      setCurrentSwingState(response.swing_state);
      onSwingStateChange?.(response.swing_state);

      // Accumulate all events for navigation history (unfiltered)
      if (response.events.length > 0) {
        setAllEvents(prev => [...prev, ...response.events]);
      }

      // Handle end of data AFTER processing bars
      if (response.end_of_data) {
        setEndOfData(true);
        isPlayingRef.current = false;  // Stop the playback loop
        clearTimers();
        setPlaybackState(PlaybackState.STOPPED);
        return;
      }

      // Filter events for linger based on event type and scale filters
      const filteredEvents = filterEvents(response.events);
      if (filteredEvents.length > 0 && lingerEnabled) {
        // Trigger linger only for filtered events when linger is enabled
        // Pass wasPlaying=true since advanceBar is called during playback
        enterLinger(filteredEvents, true);
      }
    } catch (err) {
      console.error('Failed to advance replay:', err);
      clearTimers();
      setPlaybackState(PlaybackState.PAUSED);
    } finally {
      advancePendingRef.current = false;
    }
  }, [calibrationBarCount, currentPosition, barsPerAdvance, chartAggregationScales, includeDagState, endOfData, clearTimers, enterLinger, filterEvents, lingerEnabled, onNewBars, onSwingStateChange, onAggregatedBarsChange, onDagStateChange]);

  // Ref to hold the latest advanceBar function
  const advanceBarRef = useRef<() => Promise<void>>(async () => {});

  // Keep advanceBarRef updated
  useEffect(() => {
    advanceBarRef.current = advanceBar;
  }, [advanceBar]);

  // Ref for renderNextBar to avoid stale closures
  const renderNextBarRef = useRef<() => boolean>(() => false);
  useEffect(() => {
    renderNextBarRef.current = renderNextBar;
  }, [renderNextBar]);

  // Ref for fetchBatch
  const fetchBatchRef = useRef<() => Promise<void>>(async () => {});
  useEffect(() => {
    fetchBatchRef.current = fetchBatch;
  }, [fetchBatch]);

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

    // Clear buffer and reset position tracking for clean start
    barBufferRef.current = [];
    lastFetchedPositionRef.current = currentPosition;

    // Initial fetch to fill buffer
    fetchBatchRef.current();

    // Animation timer - renders one bar at a time from buffer
    const scheduleNext = () => {
      if (!isPlayingRef.current) return;

      playbackIntervalRef.current = window.setTimeout(() => {
        if (!isPlayingRef.current) return;

        const rendered = renderNextBarRef.current();
        if (rendered && isPlayingRef.current) {
          scheduleNext();
        } else if (!rendered && !endOfData && isPlayingRef.current) {
          // Buffer empty but not end of data - wait and retry
          setTimeout(scheduleNext, 50);
        }
      }, playbackIntervalMs);
    };

    // Start animation after a short delay to let buffer fill
    setTimeout(scheduleNext, 100);
  }, [playbackState, endOfData, playbackIntervalMs, exitLinger, currentPosition]);

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

  // Step forward by speed aggregation unit (e.g., 12 5m bars when speed is 1x per 1H)
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

  // Step back through cached history (#278)
  const stepBack = useCallback(() => {
    if (playbackState === PlaybackState.LINGERING) {
      exitLinger();
    }
    if (playbackState === PlaybackState.PLAYING) {
      isPlayingRef.current = false;
      clearTimers();
    }
    setPlaybackState(PlaybackState.PAUSED);

    // Navigate backward through history buffer
    const history = historyBufferRef.current;
    if (history.length === 0) return;

    // Determine current history position
    let currentIdx = historyIndexRef.current;
    if (currentIdx < 0) {
      // At latest position, go to second-to-last snapshot
      currentIdx = history.length - 1;
    }

    // Step back one position
    const targetIdx = currentIdx - 1;
    if (targetIdx < 0) {
      // Already at oldest cached position
      return;
    }

    // Update history index and restore snapshot
    historyIndexRef.current = targetIdx;
    const snapshot = history[targetIdx];
    restoreFromSnapshot(snapshot);
  }, [playbackState, clearTimers, exitLinger, restoreFromSnapshot]);

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
    // Reset history buffer (#278)
    historyBufferRef.current = [];
    historyIndexRef.current = -1;
    setHistorySize(0);
    latestDagStateRef.current = null;
    latestAggregatedBarsRef.current = null;
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

  // Dismiss linger and resume playback only if it was playing before
  const dismissLinger = useCallback(() => {
    if (playbackState !== PlaybackState.LINGERING) return;
    const wasPlaying = wasPlayingBeforeLingerRef.current;
    exitLinger();
    if (wasPlaying) {
      startPlayback();
    }
  }, [playbackState, exitLinger, startPlayback]);

  // Pause linger timer (for feedback input focus)
  const pauseLingerTimer = useCallback(() => {
    if (playbackState !== PlaybackState.LINGERING || lingerPausedRef.current) return;

    lingerPausedRef.current = true;

    // Calculate remaining time
    if (lingerStartRef.current !== null) {
      const elapsed = Date.now() - lingerStartRef.current;
      lingerRemainingRef.current = Math.max(0, LINGER_DURATION_MS - elapsed);
    }

    // Clear the auto-advance timer
    if (lingerTimerRef.current) {
      clearTimeout(lingerTimerRef.current);
      lingerTimerRef.current = null;
    }

    // Stop animation frame (freeze the countdown)
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
  }, [playbackState]);

  // Resume linger timer (for feedback input blur)
  const resumeLingerTimer = useCallback(() => {
    if (playbackState !== PlaybackState.LINGERING || !lingerPausedRef.current) return;

    lingerPausedRef.current = false;

    // Restart from remaining time
    const remaining = lingerRemainingRef.current;
    if (remaining <= 0) {
      // Timer already expired, advance
      eventIndexRef.current++;
      if (eventIndexRef.current < eventQueueRef.current.length) {
        showCurrentEventRef.current();
      } else {
        exitLingerRef.current();
        if (wasPlayingBeforeLingerRef.current) {
          startPlaybackRef.current();
        }
      }
      return;
    }

    // Update start time to account for already elapsed time
    lingerStartRef.current = Date.now() - (LINGER_DURATION_MS - remaining);

    // Restart animation
    const animateTimer = () => {
      if (lingerStartRef.current === null || lingerPausedRef.current) return;
      const elapsed = Date.now() - lingerStartRef.current;
      const timeLeft = Math.max(0, (LINGER_DURATION_MS - elapsed) / 1000);
      setLingerTimeLeft(timeLeft);

      if (timeLeft > 0 && !lingerPausedRef.current) {
        animationFrameRef.current = requestAnimationFrame(animateTimer);
      }
    };
    animationFrameRef.current = requestAnimationFrame(animateTimer);

    // Restart auto-advance timer with remaining time
    lingerTimerRef.current = window.setTimeout(() => {
      eventIndexRef.current++;
      if (eventIndexRef.current < eventQueueRef.current.length) {
        showCurrentEventRef.current();
      } else {
        exitLingerRef.current();
        if (wasPlayingBeforeLingerRef.current) {
          startPlaybackRef.current();
        }
      }
    }, remaining);
  }, [playbackState]);

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
        // Pass wasPlaying=false since this is manual navigation
        enterLinger(filteredEventsAtBar, false);
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
        // For jumpToNextEvent, include aggregated bars and DAG state on the last iteration
        const response = await advanceReplay(
          calibrationBarCount,
          currentPosition + iterations - 1,
          1,
          chartAggregationScales,
          includeDagState
        );

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
            // Update aggregated bars and DAG state
            if (response.aggregated_bars && onAggregatedBarsChange) {
              onAggregatedBarsChange(response.aggregated_bars);
            }
            if (response.dag_state && onDagStateChange) {
              onDagStateChange(response.dag_state);
            }
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
          // Update aggregated bars and DAG state
          if (response.aggregated_bars && onAggregatedBarsChange) {
            onAggregatedBarsChange(response.aggregated_bars);
          }
          if (response.dag_state && onDagStateChange) {
            onDagStateChange(response.dag_state);
          }
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
          if (lingerEnabled) {
            // Pass wasPlaying=false since this is manual navigation
            enterLinger(filteredEvents, false);
          }
          foundEvent = true;
        }
      } catch (err) {
        console.error('Failed to advance replay:', err);
        break;
      }
    }

    advancePendingRef.current = false;
  }, [endOfData, playbackState, exitLinger, clearTimers, calibrationBarCount, currentPosition, chartAggregationScales, includeDagState, enterLinger, filterEvents, lingerEnabled, onNewBars, onSwingStateChange, onAggregatedBarsChange, onDagStateChange]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTimers();
    };
  }, [clearTimers]);

  // Compute canStepBack: at least 2 snapshots needed (one to view, one to step back to)
  // Also check historyIndex - if we're already at position 0, can't go further back
  const canStepBack = useMemo(() => {
    if (historySize < 2) return false;
    // If viewing history, check if we can go further back
    if (historyIndexRef.current >= 0) {
      return historyIndexRef.current > 0;
    }
    // At latest position, can step back if there's history
    return historySize > 1;
  }, [historySize]);

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
    // Backward navigation (#278)
    canStepBack,
    historySize,
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
    // Timer pause (for feedback input)
    pauseLingerTimer,
    resumeLingerTimer,
  };
}
