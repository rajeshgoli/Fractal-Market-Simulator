import { BarData, AggregationScale, DetectedSwing, CalibrationData, CalibrationSwing } from '../types';

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
  depth_1: CalibrationSwing[];  // Root swings (depth 0)
  depth_2: CalibrationSwing[];  // Depth 1
  depth_3: CalibrationSwing[];  // Depth 2
  deeper: CalibrationSwing[];   // Depth 3+
}

// Aggregated bars by scale (for batched playback)
export interface AggregatedBarsResponse {
  S?: BarData[];
  M?: BarData[];
  L?: BarData[];
  XL?: BarData[];
}

export interface ReplayAdvanceResponse {
  new_bars: ReplayBarData[];
  events: ReplayEvent[];
  swing_state: ReplaySwingState;
  current_bar_index: number;
  current_price: number;
  end_of_data: boolean;
  // Optional fields for batched playback
  aggregated_bars?: AggregatedBarsResponse;
  dag_state?: DagStateResponse;
}

export interface ReplayAdvanceRequest {
  calibration_bar_count: number;
  current_bar_index: number;
  advance_by?: number;
  include_aggregated_bars?: string[];  // Scales to include (e.g., ["S", "M"])
  include_dag_state?: boolean;
}

export async function advanceReplay(
  calibrationBarCount: number,
  currentBarIndex: number,
  advanceBy: number = 1,
  includeAggregatedBars?: string[],
  includeDagState?: boolean
): Promise<ReplayAdvanceResponse> {
  const requestBody: ReplayAdvanceRequest = {
    calibration_bar_count: calibrationBarCount,
    current_bar_index: currentBarIndex,
    advance_by: advanceBy,
  };
  if (includeAggregatedBars) {
    requestBody.include_aggregated_bars = includeAggregatedBars;
  }
  if (includeDagState) {
    requestBody.include_dag_state = includeDagState;
  }

  const response = await fetch(`${API_BASE}/replay/advance`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(requestBody),
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
  // Mode (replay or dag)
  mode?: 'replay' | 'dag';
  // Replay-specific context
  replay_context?: {
    selected_swing?: {
      id: string;
      scale: string;
      direction: string;
    };
    calibration_state: string;
  };
  // DAG-specific context - full data for debugging
  dag_context?: {
    active_legs: {
      leg_id: string;
      direction: 'bull' | 'bear';
      pivot_price: number;
      pivot_index: number;
      origin_price: number;
      origin_index: number;
      range: number;
    }[];
    pending_origins: {
      bull: { price: number; bar_index: number } | null;
      bear: { price: number; bar_index: number } | null;
    };
  };
  // Attached items for focused feedback (max 5)
  attachments?: FeedbackAttachment[];
}

// Attachment types for feedback
export type FeedbackAttachment =
  | { type: 'leg'; leg_id: string; direction: 'bull' | 'bear'; pivot_price: number; origin_price: number; pivot_index: number; origin_index: number }
  | { type: 'pending_origin'; direction: 'bull' | 'bear'; price: number; bar_index: number; source: string };

export interface PlaybackFeedbackResponse {
  success: boolean;
  observation_id: string;
  message: string;
}

export async function submitPlaybackFeedback(
  text: string,
  playbackBar: number,
  snapshot: PlaybackFeedbackSnapshot,
  screenshotData?: string  // Base64 encoded PNG
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
      screenshot_data: screenshotData,
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
  // Impulsiveness (0-100): Percentile rank of raw impulse vs all formed legs (#241)
  // More interpretable than raw impulse - 90+ is very impulsive, 10- is gradual
  impulsiveness: number | null;
  // Spikiness (0-100): Sigmoid-normalized skewness of bar contributions (#241)
  // 50 = neutral, 90+ = spike-driven, 10- = evenly distributed
  spikiness: number | null;
  // Hierarchy fields for exploration (#250, #251)
  parent_leg_id: string | null;
  swing_id: string | null;
}

export interface DagPendingOrigin {
  price: number;
  bar_index: number;
  direction: 'bull' | 'bear';
  source: 'high' | 'low' | 'open' | 'close';
}

export interface DagStateResponse {
  active_legs: DagLeg[];
  pending_origins: {
    bull: DagPendingOrigin | null;
    bear: DagPendingOrigin | null;
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

// Types for hierarchy exploration (Issue #250)
export interface LegLineageResponse {
  leg_id: string;
  ancestors: string[];  // Ordered from immediate parent to root
  descendants: string[];  // All descendant leg IDs
  depth: number;  // 0 = root
}

export async function fetchLegLineage(legId: string): Promise<LegLineageResponse> {
  const response = await fetch(`${API_BASE}/dag/lineage/${encodeURIComponent(legId)}`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `Failed to fetch leg lineage: ${response.statusText}`);
  }
  return response.json();
}
