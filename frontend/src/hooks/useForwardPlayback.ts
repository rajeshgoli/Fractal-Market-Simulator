import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { PlaybackState, BarData, FilterState } from '../types';
import { advanceReplay, reverseReplay, resetDag, ReplayEvent, ReplaySwingState, AggregatedBarsResponse, DagStateResponse, RefStateSnapshot } from '../lib/api';
import { formatReplayBarsData } from '../utils/barDataUtils';
import { LINGER_DURATION_MS } from '../constants';

// Fetch batch size for non-DAG mode (bars only, can batch aggressively)
const FETCH_BATCH_SIZE = 100;

// Refill threshold - trigger fetch when buffer drops below this
const BUFFER_REFILL_THRESHOLD = 50;

interface UseForwardPlaybackOptions {
  calibrationBarCount: number;
  calibrationBars: BarData[];
  playbackIntervalMs: number;
  barsPerAdvance: number;  // How many source bars to advance per tick (aggregation factor)
  barsPerRender?: number;  // How many bars to render per tick (for speed compensation, default 1)
  filters: FilterState[];  // Event type filters
  lingerEnabled?: boolean;  // Whether to pause on events (default: true)
  chartAggregationScales?: string[];  // Scales to include in response (e.g., ["S", "M"])
  includeDagState?: boolean;  // Whether to include DAG state in response
  includePerBarRefStates?: boolean;  // Whether to include per-bar reference states (#456)
  onNewBars?: (bars: BarData[]) => void;
  onSwingStateChange?: (state: ReplaySwingState) => void;
  onAggregatedBarsChange?: (bars: AggregatedBarsResponse) => void;  // Called with aggregated bars
  onDagStateChange?: (state: DagStateResponse) => void;  // Called with DAG state
  onRefStateChange?: (state: RefStateSnapshot) => void;  // Called with per-bar reference state (#456)
  onReset?: () => void;  // Called when jumpToStart resets playback state
}

interface UseForwardPlaybackReturn {
  playbackState: PlaybackState;
  currentPosition: number;
  csvIndex: number;  // Authoritative CSV row index from backend (#297)
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
  canStepBack: boolean;  // Whether step back is available (not at start)
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
  // External sync (for Process Till feature)
  syncToPosition: (newPosition: number, newBars: BarData[], newCsvIndex: number, events?: ReplayEvent[]) => void;
  // Buffer management (#458)
  clearRefStateBuffer: () => void;  // Invalidate ref state buffer (e.g., on config change)
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
  includePerBarRefStates = false,
  onNewBars,
  onSwingStateChange,
  onAggregatedBarsChange,
  onDagStateChange,
  onRefStateChange,
  onReset,
}: UseForwardPlaybackOptions): UseForwardPlaybackReturn {
  // Playback state
  const [playbackState, setPlaybackState] = useState<PlaybackState>(PlaybackState.STOPPED);
  const [currentPosition, setCurrentPosition] = useState(calibrationBarCount - 1);
  const [csvIndex, setCsvIndex] = useState(0);  // Authoritative CSV row index from backend (#297)
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

  // Store latest DAG state and aggregated bars
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
  const playbackIntervalMsRef = useRef(playbackIntervalMs); // Ref for interval to allow mid-playback speed changes (#316)

  // Bar buffer for smooth animation (batched fetch, individual render)
  interface BufferedBar {
    bar: BarData;
    events: ReplayEvent[];
    dagState?: DagStateResponse;  // Per-bar DAG state for DAG mode (#283)
    refState?: RefStateSnapshot;  // Per-bar reference state (#456)
  }
  const barBufferRef = useRef<BufferedBar[]>([]);
  const lastFetchedPositionRef = useRef(calibrationBarCount - 1);
  const isFetchingRef = useRef(false);

  // Queue of pending states from batch fetches - each entry is applied when we reach its target bar
  // This prevents the overwrite race condition where a new batch overwrites pending state before it's applied
  interface PendingBatchState {
    targetBarIndex: number;
    aggregatedBars: import('../lib/api').AggregatedBarsResponse | null;
    dagState: import('../lib/api').DagStateResponse | null;  // Fallback only
    swingState: ReplaySwingState | null;
    csvIndex: number;
  }
  const pendingBatchStatesRef = useRef<PendingBatchState[]>([]);

  // Ref to hold the latest functions (avoids stale closures)
  const showCurrentEventRef = useRef<() => void>(() => {});
  const exitLingerRef = useRef<() => void>(() => {});
  const startPlaybackRef = useRef<() => void>(() => {});

  // Initialize visible bars from calibration
  useEffect(() => {
    setVisibleBars(calibrationBars);
    setCurrentPosition(calibrationBarCount - 1);
  }, [calibrationBars, calibrationBarCount]);

  // Keep playbackIntervalMsRef updated for mid-playback speed changes (#316)
  useEffect(() => {
    playbackIntervalMsRef.current = playbackIntervalMs;
  }, [playbackIntervalMs]);

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
    setLingerSwingId(event.leg_id);
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
      return enabledEventTypes.has(event.type);
    });
  }, [filters]);

  // Fetch a batch of bars into the buffer (background fetch)
  // Used for both DAG and non-DAG modes for smooth high-speed playback (#283)
  const fetchBatch = useCallback(async () => {
    if (endOfData || isFetchingRef.current) {
      return;
    }

    isFetchingRef.current = true;
    try {
      // Fetch from the last fetched position using fixed batch size
      // In DAG mode, request per-bar DAG states for accurate per-bar visualization (#283)
      // In Reference mode, request per-bar ref states for efficient batched fetching (#456)
      // Pass fromIndex for BE resync if needed (#310)
      const response = await advanceReplay(
        calibrationBarCount,
        lastFetchedPositionRef.current,
        FETCH_BATCH_SIZE,
        chartAggregationScales,
        false,  // include_dag_state (final bar only) - we use per-bar instead
        includeDagState,  // include_per_bar_dag_states - reuse the includeDagState prop
        lastFetchedPositionRef.current,  // fromIndex for BE resync
        includePerBarRefStates  // include_per_bar_ref_states (#456)
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

        // Add bars to buffer with per-bar DAG states (#283) and ref states (#456)
        const newBufferedBars: typeof barBufferRef.current = response.new_bars.map((bar, i) => ({
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
          // Associate per-bar DAG state if available (#283)
          dagState: response.dag_states?.[i],
          // Associate per-bar ref state if available (#456)
          refState: response.ref_states?.[i],
        }));

        barBufferRef.current = [...barBufferRef.current, ...newBufferedBars];
        lastFetchedPositionRef.current = response.current_bar_index;

        // Apply aggregated bars IMMEDIATELY so chart has candles for legs to render against
        // Legs update incrementally via per-bar DAG states in the buffer
        if (response.aggregated_bars && onAggregatedBarsChange) {
          onAggregatedBarsChange(response.aggregated_bars);
          latestAggregatedBarsRef.current = response.aggregated_bars;
        }

        // Queue other batch state (swing state, csv index) - these are deferred
        pendingBatchStatesRef.current.push({
          targetBarIndex: response.current_bar_index,
          aggregatedBars: null,  // Already applied above
          dagState: (response.dag_state && !response.dag_states) ? response.dag_state : null,
          swingState: response.swing_state,
          csvIndex: response.csv_index,
        });

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
  }, [calibrationBarCount, chartAggregationScales, includeDagState, includePerBarRefStates, endOfData, onAggregatedBarsChange]);

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
    const { bar, events, dagState, refState } = buffer.shift()!;

    // Render the bar - use functional update to get latest state for snapshot
    let newVisibleBars: BarData[] = [];
    let newAllEvents: ReplayEvent[] = [];
    setVisibleBars(prev => {
      newVisibleBars = [...prev, bar];
      return newVisibleBars;
    });
    setCurrentPosition(bar.index);
    onNewBars?.([bar]);

    // Apply per-bar DAG state immediately if available (#283)
    if (dagState && onDagStateChange) {
      onDagStateChange(dagState);
      latestDagStateRef.current = dagState;
    }

    // Apply per-bar ref state immediately if available (#456)
    if (refState && onRefStateChange) {
      onRefStateChange(refState);
    }

    // Apply pending batch states when we reach their target bar index
    // Process all batch states that have been reached (queue may have multiple entries)
    while (pendingBatchStatesRef.current.length > 0) {
      const nextState = pendingBatchStatesRef.current[0];
      if (bar.index >= nextState.targetBarIndex) {
        // Remove from queue
        pendingBatchStatesRef.current.shift();

        // Apply aggregated bars
        if (nextState.aggregatedBars && onAggregatedBarsChange) {
          onAggregatedBarsChange(nextState.aggregatedBars);
          latestAggregatedBarsRef.current = nextState.aggregatedBars;
        }

        // Fallback DAG state (only used when per-bar dag_states not available)
        if (nextState.dagState && onDagStateChange) {
          onDagStateChange(nextState.dagState);
          latestDagStateRef.current = nextState.dagState;
        }

        // Apply swing state
        if (nextState.swingState) {
          setCurrentSwingState(nextState.swingState);
          onSwingStateChange?.(nextState.swingState);
        }

        // Apply authoritative CSV index from backend (#297)
        setCsvIndex(nextState.csvIndex);
      } else {
        // Not yet reached, stop processing queue
        break;
      }
    }

    // Accumulate events for history snapshot
    setAllEvents(prev => {
      newAllEvents = events.length > 0 ? [...prev, ...events] : prev;
      return newAllEvents;
    });

    // Check for events that should trigger linger
    const filteredEvents = filterEvents(events);
    if (filteredEvents.length > 0 && lingerEnabled) {
      enterLinger(filteredEvents, true);
      return true; // Bar rendered, but entering linger
    }

    // Trigger background fetch if buffer is running low
    if (buffer.length < BUFFER_REFILL_THRESHOLD && !isFetchingRef.current && !endOfData) {
      fetchBatch();
    }

    return true; // Bar rendered successfully
  }, [endOfData, clearTimers, filterEvents, lingerEnabled, enterLinger, fetchBatch, onNewBars, onAggregatedBarsChange, onDagStateChange, onRefStateChange, onSwingStateChange]);

  // Direct API call for manual stepping (stepForward, jumpToNextEvent)
  // Buffer-based renderNextBar is for smooth continuous playback only
  // Returns events and endOfData status for caller inspection (e.g., jumpToNextEvent)
  const advanceBar = useCallback(async (opts?: {
    barsToAdvance?: number;  // Override barsPerAdvance (default: use hook's barsPerAdvance)
    triggerLinger?: boolean;  // Whether to trigger linger on events (default: true)
  }): Promise<{ events: ReplayEvent[]; endOfData: boolean }> => {
    const { barsToAdvance = barsPerAdvance, triggerLinger = true } = opts ?? {};

    if (endOfData || advancePendingRef.current) {
      return { events: [], endOfData };
    }

    advancePendingRef.current = true;
    try {
      // Request aggregated bars and DAG state in the same API call
      // Use barsToAdvance to step by speed aggregation unit (e.g., 12 5m bars for 1H speed)
      // Pass fromIndex (currentPosition) for BE resync if needed (#310)
      const response = await advanceReplay(
        calibrationBarCount,
        currentPosition,
        barsToAdvance,
        chartAggregationScales,
        includeDagState,
        false,  // include_per_bar_dag_states
        currentPosition  // fromIndex for BE resync
      );

      // Track new state for history snapshot
      let newVisibleBars: BarData[] = [];
      let newAllEvents: ReplayEvent[] = [];

      // Append new bars (process even if end_of_data to update UI correctly)
      if (response.new_bars.length > 0) {
        const newBarData = formatReplayBarsData(response.new_bars);

        setVisibleBars(prev => {
          newVisibleBars = [...prev, ...newBarData];
          return newVisibleBars;
        });
        // Use the last bar's index from new_bars, not response.current_bar_index
        // This prevents jumping ahead when backend state is ahead of rendered state
        const lastBarIndex = newBarData[newBarData.length - 1].index;
        setCurrentPosition(lastBarIndex);
        onNewBars?.(newBarData);

        // Update lastFetchedPosition to the actual position we rendered to
        lastFetchedPositionRef.current = lastBarIndex;
      }

      // Update aggregated bars from response (replaces separate API call)
      if (response.aggregated_bars && onAggregatedBarsChange) {
        onAggregatedBarsChange(response.aggregated_bars);
        latestAggregatedBarsRef.current = response.aggregated_bars;
      }

      // Update DAG state from response (replaces separate API call)
      if (response.dag_state && onDagStateChange) {
        onDagStateChange(response.dag_state);
        latestDagStateRef.current = response.dag_state;
      }

      // Update swing state
      setCurrentSwingState(response.swing_state);
      onSwingStateChange?.(response.swing_state);

      // Update authoritative CSV index from backend (#297)
      setCsvIndex(response.csv_index);

      // Accumulate all events for navigation history (unfiltered)
      if (response.events.length > 0) {
        setAllEvents(prev => {
          newAllEvents = [...prev, ...response.events];
          return newAllEvents;
        });
      } else {
        // Get current events for snapshot
        setAllEvents(prev => {
          newAllEvents = prev;
          return prev;
        });
      }

      // Handle end of data AFTER processing bars
      if (response.end_of_data) {
        setEndOfData(true);
        isPlayingRef.current = false;  // Stop the playback loop
        clearTimers();
        setPlaybackState(PlaybackState.STOPPED);
        return { events: response.events, endOfData: true };
      }

      // Filter events for linger based on event type and scale filters
      if (triggerLinger) {
        const filteredEvents = filterEvents(response.events);
        if (filteredEvents.length > 0 && lingerEnabled) {
          // Trigger linger only for filtered events when linger is enabled
          // Pass wasPlaying=true since advanceBar is called during playback
          enterLinger(filteredEvents, true);
        }
      }

      return { events: response.events, endOfData: false };
    } catch (err) {
      console.error('Failed to advance replay:', err);
      clearTimers();
      setPlaybackState(PlaybackState.PAUSED);
      return { events: [], endOfData: false };
    } finally {
      advancePendingRef.current = false;
    }
  }, [calibrationBarCount, currentPosition, barsPerAdvance, chartAggregationScales, includeDagState, endOfData, clearTimers, enterLinger, filterEvents, lingerEnabled, onNewBars, onSwingStateChange, onAggregatedBarsChange, onDagStateChange]);

  // Ref to hold the latest advanceBar function
  const advanceBarRef = useRef<(opts?: { barsToAdvance?: number; triggerLinger?: boolean }) => Promise<{ events: ReplayEvent[]; endOfData: boolean }>>(async () => ({ events: [], endOfData: false }));

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
  // Uses buffered fetching for smooth high-speed playback in both modes (#283)
  // In DAG mode, per-bar DAG states are fetched with each batch and applied per-bar
  const startPlayback = useCallback(() => {
    if (playbackState === PlaybackState.LINGERING) {
      exitLinger();
    }

    if (endOfData) {
      return;
    }

    isPlayingRef.current = true;
    setPlaybackState(PlaybackState.PLAYING);

    // Buffered fetching for smooth high-speed playback in both modes (#283)
    // Clear buffer, pending batch queue, and reset position tracking for clean start
    barBufferRef.current = [];
    pendingBatchStatesRef.current = [];
    lastFetchedPositionRef.current = currentPosition;

    // Initial fetch to fill buffer
    fetchBatchRef.current();

    // Animation timer - renders one bar at a time from buffer
    // Uses ref for interval to support mid-playback speed changes (#316)
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
      }, playbackIntervalMsRef.current);  // Use ref for live speed updates
    };

    // Start animation after a short delay to let buffer fill
    setTimeout(scheduleNext, 100);
  }, [playbackState, endOfData, exitLinger, currentPosition]);

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
  // When lingering, space/click should PAUSE (not resume) - gives user control (#311)
  const togglePlayPause = useCallback(() => {
    if (playbackState === PlaybackState.LINGERING) {
      exitLinger();
      setPlaybackState(PlaybackState.PAUSED);
    } else if (playbackState === PlaybackState.PLAYING) {
      pause();
    } else {
      startPlayback();
    }
  }, [playbackState, startPlayback, pause, exitLinger]);

  // Step forward by advancing one bar
  const stepForward = useCallback(async () => {
    if (playbackState === PlaybackState.LINGERING) {
      exitLinger();
    }
    if (playbackState === PlaybackState.PLAYING) {
      isPlayingRef.current = false;
      clearTimers();
    }
    // Clear buffer and pending queue to prevent in-flight fetchBatch from overwriting state
    // Also reset lastFetchedPosition so advanceBar resyncs backend to current position
    barBufferRef.current = [];
    pendingBatchStatesRef.current = [];
    lastFetchedPositionRef.current = currentPosition;
    setPlaybackState(PlaybackState.PAUSED);
    await advanceBar();
  }, [playbackState, currentPosition, clearTimers, exitLinger, advanceBar]);

  // Step back by calling backend to replay from 0 to current-1
  const stepBack = useCallback(async () => {
    if (playbackState === PlaybackState.LINGERING) {
      exitLinger();
    }
    if (playbackState === PlaybackState.PLAYING) {
      isPlayingRef.current = false;
      clearTimers();
    }
    setPlaybackState(PlaybackState.PAUSED);

    // Can't step back from start
    if (currentPosition <= 0) {
      return;
    }

    try {
      // Call backend to reverse one bar
      const response = await reverseReplay(
        currentPosition,
        chartAggregationScales,
        includeDagState
      );

      // Update position
      setCurrentPosition(response.current_bar_index);

      // Trim visible bars to match new position
      setVisibleBars(prev => prev.slice(0, response.current_bar_index + 1));

      // Update swing state
      if (response.swing_state) {
        setCurrentSwingState(response.swing_state);
        onSwingStateChange?.(response.swing_state);
      }

      // Update aggregated bars
      if (response.aggregated_bars && onAggregatedBarsChange) {
        onAggregatedBarsChange(response.aggregated_bars);
        latestAggregatedBarsRef.current = response.aggregated_bars;
      }

      // Update DAG state
      if (response.dag_state && onDagStateChange) {
        onDagStateChange(response.dag_state);
        latestDagStateRef.current = response.dag_state;
      }

      // Update authoritative CSV index from backend (#297)
      setCsvIndex(response.csv_index);

      // Update last fetched position to stay in sync
      lastFetchedPositionRef.current = response.current_bar_index;

      // Clear bar buffer since we've gone backward
      barBufferRef.current = [];

    } catch (error) {
      console.error('Failed to step back:', error);
    }
  }, [playbackState, currentPosition, clearTimers, exitLinger, chartAggregationScales, includeDagState, onSwingStateChange, onAggregatedBarsChange, onDagStateChange]);

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
    latestDagStateRef.current = null;
    latestAggregatedBarsRef.current = null;
    pendingBatchStatesRef.current = [];  // Clear pending batch queue

    // Notify parent of reset so it can clear its own state
    onReset?.();

    // Reset backend detector state
    resetDag().catch((error) => {
      console.error('Failed to reset DAG backend:', error);
    });
  }, [clearTimers, exitLinger, calibrationBars, calibrationBarCount, onReset]);

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

  // Dismiss linger (ESC/X) and resume playback - user wants to skip the linger
  // Use Space/pause button to actually pause (#311)
  const dismissLinger = useCallback(() => {
    if (playbackState !== PlaybackState.LINGERING) return;
    exitLinger();
    startPlayback();
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
  // Reuses advanceBar for API response handling to avoid duplication
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

      // Use advanceBar with triggerLinger=false so we can control linger manually
      const { events, endOfData: reachedEnd } = await advanceBarRef.current({
        barsToAdvance: 1,
        triggerLinger: false,
      });

      if (reachedEnd) break;

      // Check for filtered events (only linger on events matching filters)
      const filteredEvents = filterEvents(events);
      if (filteredEvents.length > 0) {
        if (lingerEnabled) {
          // Pass wasPlaying=false since this is manual navigation
          enterLinger(filteredEvents, false);
        }
        foundEvent = true;
      }
    }
  }, [endOfData, playbackState, exitLinger, clearTimers, enterLinger, filterEvents, lingerEnabled]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTimers();
    };
  }, [clearTimers]);

  // Compute canStepBack: can step back if not at the start
  // Now uses backend API instead of cached history
  const canStepBack = useMemo(() => {
    return currentPosition > 0;
  }, [currentPosition]);

  // Sync to external position (used when external code advances bars directly)
  // This updates internal state to match the new position without re-fetching
  const syncToPosition = useCallback((newPosition: number, newBars: BarData[], newCsvIndex: number, events?: ReplayEvent[]) => {
    // Clear buffers since external code has already processed
    barBufferRef.current = [];
    pendingBatchStatesRef.current = [];
    lastFetchedPositionRef.current = newPosition;

    // Update state
    setCurrentPosition(newPosition);
    setVisibleBars(newBars);
    setCsvIndex(newCsvIndex);

    // Merge events if provided (for stats tracking)
    if (events && events.length > 0) {
      setAllEvents(prev => [...prev, ...events]);
    }
  }, []);

  // Clear ref state buffer (#458: for config change invalidation)
  // When salience config changes, buffered ref states have stale rankings
  const clearRefStateBuffer = useCallback(() => {
    barBufferRef.current = [];
    pendingBatchStatesRef.current = [];
  }, []);

  return {
    playbackState,
    currentPosition,
    csvIndex,  // Authoritative CSV row index from backend (#297)
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
    // Backward navigation
    canStepBack,
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
    // External sync (for Process Till feature)
    syncToPosition,
    // Buffer management (#458)
    clearRefStateBuffer,
  };
}
