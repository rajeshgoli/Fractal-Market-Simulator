import { BarData, AggregationScale, DetectedSwing, CalibrationData } from '../types';

const API_BASE = '/api';

// App configuration (mode, etc.)
export interface AppConfig {
  mode: 'calibration' | 'dag';
}

export async function fetchConfig(): Promise<AppConfig> {
  const response = await fetch(`${API_BASE}/config`);
  if (!response.ok) {
    throw new Error(`Failed to fetch config: ${response.statusText}`);
  }
  return response.json();
}

export interface SessionInfo {
  session_id: string;
  data_file: string;
  resolution: string;
  window_size: number;
  window_offset: number;
  total_source_bars: number;
  calibration_bar_count: number | null;
  scale: string;
  created_at: string;
  annotation_count: number;
  completed_scales: string[];
}

export async function fetchSession(): Promise<SessionInfo> {
  const response = await fetch(`${API_BASE}/session`);
  if (!response.ok) {
    throw new Error(`Failed to fetch session: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchBars(scale?: AggregationScale): Promise<BarData[]> {
  const url = scale ? `${API_BASE}/bars?scale=${scale}` : `${API_BASE}/bars`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch bars: ${response.statusText}`);
  }
  return response.json();
}

export interface WindowedSwingsResponse {
  bar_end: number;
  swing_count: number;
  swings: DetectedSwing[];
}

export async function fetchDetectedSwings(
  barEnd: number,
  topN: number = 2
): Promise<WindowedSwingsResponse> {
  const response = await fetch(
    `${API_BASE}/swings/windowed?bar_end=${barEnd}&top_n=${topN}`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch detected swings: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchCalibration(barCount: number = 10000): Promise<CalibrationData> {
  const response = await fetch(`${API_BASE}/replay/calibrate?bar_count=${barCount}`);
  if (!response.ok) {
    throw new Error(`Failed to run calibration: ${response.statusText}`);
  }
  return response.json();
}

// Types for replay advance
export interface ReplayBarData {
  index: number;
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface ReplayEvent {
  type: 'SWING_FORMED' | 'SWING_INVALIDATED' | 'SWING_COMPLETED' | 'LEVEL_CROSS' | 'LEG_CREATED' | 'LEG_PRUNED' | 'LEG_INVALIDATED';
  bar_index: number;
  scale: string;
  direction: string;
  swing_id: string;
  swing?: {
    id: string;
    scale: string;
    direction: string;
    high_price: number;
    high_bar_index: number;
    low_price: number;
    low_bar_index: number;
    size: number;
    rank: number;
    is_active: boolean;
    fib_0: number;
    fib_0382: number;
    fib_1: number;
    fib_2: number;
  };
  level?: number;
  previous_level?: number;
  trigger_explanation?: string;
}

export interface ReplaySwingState {
  XL: CalibrationData['active_swings_by_scale']['XL'];
  L: CalibrationData['active_swings_by_scale']['L'];
  M: CalibrationData['active_swings_by_scale']['M'];
  S: CalibrationData['active_swings_by_scale']['S'];
}

export interface ReplayAdvanceResponse {
  new_bars: ReplayBarData[];
  events: ReplayEvent[];
  swing_state: ReplaySwingState;
  current_bar_index: number;
  current_price: number;
  end_of_data: boolean;
}

export async function advanceReplay(
  calibrationBarCount: number,
  currentBarIndex: number,
  advanceBy: number = 1
): Promise<ReplayAdvanceResponse> {
  const response = await fetch(`${API_BASE}/replay/advance`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      calibration_bar_count: calibrationBarCount,
      current_bar_index: currentBarIndex,
      advance_by: advanceBy,
    }),
  });
  if (!response.ok) {
    throw new Error(`Failed to advance replay: ${response.statusText}`);
  }
  return response.json();
}

// Types for playback feedback
export interface PlaybackFeedbackEventContext {
  event_type?: string;
  scale?: string;
  swing?: {
    high_bar_index: number;
    low_bar_index: number;
    high_price: string;
    low_price: string;
    direction: string;
  };
  detection_bar_index?: number;
}

// Rich context snapshot for always-on feedback
export interface PlaybackFeedbackSnapshot {
  // Current state
  state: 'calibrating' | 'calibration_complete' | 'playing' | 'paused';
  // Session offset
  window_offset: number;
  // Bars elapsed since calibration
  bars_since_calibration: number;
  // Current bar index
  current_bar_index: number;
  // Calibration bar count
  calibration_bar_count: number;
  // Swing counts by scale
  swings_found: {
    XL: number;
    L: number;
    M: number;
    S: number;
  };
  // Event-related counts (from allEvents)
  swings_invalidated: number;
  swings_completed: number;
  // Optional event context (if during linger)
  event_context?: PlaybackFeedbackEventContext;
}

export interface PlaybackFeedbackResponse {
  success: boolean;
  observation_id: string;
  message: string;
}

export async function submitPlaybackFeedback(
  text: string,
  playbackBar: number,
  snapshot: PlaybackFeedbackSnapshot
): Promise<PlaybackFeedbackResponse> {
  const response = await fetch(`${API_BASE}/playback/feedback`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      text,
      playback_bar: playbackBar,
      snapshot,
    }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `Failed to submit feedback: ${response.statusText}`);
  }
  return response.json();
}

// Types for DAG state (Issue #169)
export interface DagLeg {
  leg_id: string;
  direction: 'bull' | 'bear';
  pivot_price: number;
  pivot_index: number;
  origin_price: number;
  origin_index: number;
  retracement_pct: number;
  formed: boolean;
  status: 'active' | 'stale' | 'invalidated';
  bar_count: number;
}

export interface DagOrphanedOrigin {
  price: number;
  bar_index: number;
}

export interface DagPendingPivot {
  price: number;
  bar_index: number;
  direction: 'bull' | 'bear';
  source: 'high' | 'low' | 'open' | 'close';
}

export interface DagStateResponse {
  active_legs: DagLeg[];
  orphaned_origins: {
    bull: DagOrphanedOrigin[];
    bear: DagOrphanedOrigin[];
  };
  pending_pivots: {
    bull: DagPendingPivot | null;
    bear: DagPendingPivot | null;
  };
  leg_counts: {
    bull: number;
    bear: number;
  };
}

export async function fetchDagState(): Promise<DagStateResponse> {
  const response = await fetch(`${API_BASE}/dag/state`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `Failed to fetch DAG state: ${response.statusText}`);
  }
  return response.json();
}
