import { BarData, AggregationScale, CalibrationData, CalibrationSwing, DetectionConfig } from '../types';

const API_BASE = '/api';

// ============================================================================
// File Discovery Types (#325)
// ============================================================================

export interface DataFileInfo {
  path: string;
  name: string;
  total_bars: number;
  resolution: string;
  start_date: string | null;
  end_date: string | null;
}

export async function fetchDataFiles(): Promise<DataFileInfo[]> {
  const response = await fetch(`${API_BASE}/files`);
  if (!response.ok) {
    throw new Error(`Failed to fetch data files: ${response.statusText}`);
  }
  return response.json();
}

// ============================================================================
// Session Restart Types (#326, #327)
// ============================================================================

export interface SessionRestartRequest {
  data_file: string;
  start_date?: string;  // ISO date string (YYYY-MM-DD)
}

export interface SessionRestartResponse {
  success: boolean;
  session_id: string;
  data_file: string;
  resolution: string;
  window_size: number;
  window_offset: number;
  total_source_bars: number;
  start_date?: string;
}

export async function restartSession(request: SessionRestartRequest): Promise<SessionRestartResponse> {
  const response = await fetch(`${API_BASE}/session/restart`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `Failed to restart session: ${response.statusText}`);
  }
  return response.json();
}

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
  current_bar_index: number | null;  // Current playback position (-1 = not started, null = no session)
  scale: string;
  created_at: string;
  annotation_count: number;
  completed_scales: string[];
  initialized?: boolean;  // Whether backend has an active session
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
  csv_index: number;  // Original row index in source CSV file
}

export interface ReplayEvent {
  type: 'SWING_FORMED' | 'SWING_INVALIDATED' | 'SWING_COMPLETED' | 'LEG_CREATED' | 'LEG_PRUNED' | 'LEG_INVALIDATED' | 'ORIGIN_BREACHED';
  bar_index: number;
  scale: string;
  direction: string;
  leg_id: string;
  swing?: {
    // Unified LegResponse fields (Issue #398)
    leg_id: string;
    direction: string;
    origin_price: number;
    origin_index: number;
    pivot_price: number;
    pivot_index: number;
    range: number;
    rank: number;
    is_active: boolean;
    depth: number;
    parent_leg_id: string | null;
    fib_levels?: Record<string, number>;
    scale?: string;
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
  '1m'?: BarData[];
  '5m'?: BarData[];
  '15m'?: BarData[];
  '30m'?: BarData[];
  '1H'?: BarData[];
  '4H'?: BarData[];
  '1D'?: BarData[];
  '1W'?: BarData[];
}

export interface ReplayAdvanceResponse {
  new_bars: ReplayBarData[];
  events: ReplayEvent[];
  swing_state: ReplaySwingState;
  current_bar_index: number;
  current_price: number;
  end_of_data: boolean;
  csv_index: number;  // Authoritative CSV row index (window_offset + current_bar_index)
  // Optional fields for batched playback
  aggregated_bars?: AggregatedBarsResponse;
  dag_state?: DagStateResponse;  // DAG state at final bar only
  dag_states?: DagStateResponse[];  // Per-bar DAG states (#283)
}

export interface ReplayAdvanceRequest {
  calibration_bar_count: number;
  current_bar_index: number;
  advance_by?: number;
  include_aggregated_bars?: string[];  // Scales to include (e.g., ["S", "M"])
  include_dag_state?: boolean;  // DAG state at final bar only
  include_per_bar_dag_states?: boolean;  // Per-bar DAG states (#283)
  from_index?: number;  // FE position for BE resync if diverged (#310)
}

export async function advanceReplay(
  calibrationBarCount: number,
  currentBarIndex: number,
  advanceBy: number = 1,
  includeAggregatedBars?: string[],
  includeDagState?: boolean,
  includePerBarDagStates?: boolean,
  fromIndex?: number
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
  if (includePerBarDagStates) {
    requestBody.include_per_bar_dag_states = includePerBarDagStates;
  }
  if (fromIndex !== undefined) {
    requestBody.from_index = fromIndex;
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

// Reverse replay request
export interface ReplayReverseRequest {
  current_bar_index: number;
  include_aggregated_bars?: string[];
  include_dag_state?: boolean;
}

export async function reverseReplay(
  currentBarIndex: number,
  includeAggregatedBars?: string[],
  includeDagState?: boolean
): Promise<ReplayAdvanceResponse> {
  const requestBody: ReplayReverseRequest = {
    current_bar_index: currentBarIndex,
  };
  if (includeAggregatedBars) {
    requestBody.include_aggregated_bars = includeAggregatedBars;
  }
  if (includeDagState) {
    requestBody.include_dag_state = includeDagState;
  }

  const response = await fetch(`${API_BASE}/replay/reverse`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(requestBody),
  });
  if (!response.ok) {
    throw new Error(`Failed to reverse replay: ${response.statusText}`);
  }
  return response.json();
}

// Types for playback feedback
export interface PlaybackFeedbackEventContext {
  event_type?: string;
  scale?: string;
  swing?: {
    // Unified origin/pivot terminology (Issue #398)
    origin_bar_index: number;
    pivot_bar_index: number;
    origin_price: string;
    pivot_price: string;
    direction: string;
  };
  detection_bar_index?: number;
}

// Detection config captured in feedback snapshot (#320, #404 simplified - symmetric config)
export interface FeedbackDetectionConfig {
  stale_extension_threshold: number;
  origin_range_threshold: number;
  origin_time_threshold: number;
  max_turns: number;  // Max legs per pivot (#404)
  engulfed_breach_threshold: number;  // Symmetric engulfed threshold (#404)
}

// Rich context snapshot for always-on feedback
export interface PlaybackFeedbackSnapshot {
  // Current state
  state: 'calibrating' | 'calibration_complete' | 'playing' | 'paused';
  // Authoritative CSV row index for current position (from backend)
  csv_index: number;
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
  // Detection config at time of observation (#320)
  detection_config?: FeedbackDetectionConfig;
}

// Attachment types for feedback
export type FeedbackAttachment =
  | { type: 'leg'; leg_id: string; direction: 'bull' | 'bear'; pivot_price: number; origin_price: number; pivot_index: number; origin_index: number; csv_index?: number }
  | { type: 'pending_origin'; direction: 'bull' | 'bear'; price: number; bar_index: number; source: string; csv_index?: number }
  | { type: 'lifecycle_event'; leg_id: string; leg_direction: 'bull' | 'bear'; event_type: string; bar_index: number; csv_index: number; timestamp: string; explanation: string };

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
  status: 'active' | 'stale';  // #345: 'invalidated' removed, use origin_breached
  origin_breached: boolean;    // #345: True if origin was breached (structural invalidation)
  bar_count: number;
  // Impulsiveness (0-100): Percentile rank of raw impulse vs all formed legs (#241)
  // More interpretable than raw impulse - 90+ is very impulsive, 10- is gradual
  impulsiveness: number | null;
  // Spikiness (0-100): Sigmoid-normalized skewness of bar contributions (#241)
  // 50 = neutral, 90+ = spike-driven, 10- = evenly distributed
  spikiness: number | null;
  // Hierarchy fields for exploration (#250, #251)
  parent_leg_id: string | null;
  // Segment impulse tracking (#307): Two-impulse model for parent segments
  // impulse_to_deepest: Price change per bar from origin to deepest point
  impulse_to_deepest: number | null;
  // impulse_back: Price change per bar from deepest back to child origin
  impulse_back: number | null;
  // net_segment_impulse: impulse_to_deepest - impulse_back (sustained conviction)
  net_segment_impulse: number | null;
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

// Types for Follow Leg feature (Issue #267)
export interface LifecycleEvent {
  leg_id: string;
  event_type: 'formed' | 'origin_breached' | 'pivot_breached' | 'engulfed' | 'pruned' | 'invalidated';
  bar_index: number;
  csv_index: number;
  timestamp: string;
  explanation: string;
}

export interface FollowedLegsEventsResponse {
  events: LifecycleEvent[];
}

export async function fetchFollowedLegsEvents(
  legIds: string[],
  sinceBar: number
): Promise<FollowedLegsEventsResponse> {
  const legIdsParam = legIds.join(',');
  const response = await fetch(
    `${API_BASE}/followed-legs/events?leg_ids=${encodeURIComponent(legIdsParam)}&since_bar=${sinceBar}`
  );
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `Failed to fetch followed legs events: ${response.statusText}`);
  }
  return response.json();
}

// ============================================================================
// Detection Config API (Issue #288 - Detection Config UI Panel)
// ============================================================================

/**
 * Request to update detection configuration.
 * Only provided fields are updated; omitted fields keep defaults.
 * #404: All thresholds are symmetric (apply to both bull and bear).
 */
export interface DetectionConfigUpdateRequest {
  stale_extension_threshold?: number;
  origin_range_threshold?: number;  // Origin proximity range threshold (#294)
  origin_time_threshold?: number;  // Origin proximity time threshold (#294)
  max_turns?: number;  // Max legs per pivot (#404)
  engulfed_breach_threshold?: number;  // Symmetric engulfed threshold (#404)
}

/**
 * Fetch current detection configuration.
 */
export async function fetchDetectionConfig(): Promise<DetectionConfig> {
  const response = await fetch(`${API_BASE}/replay/config`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `Failed to fetch detection config: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Update detection configuration and re-calibrate.
 * Returns the updated configuration after re-calibration.
 */
export async function updateDetectionConfig(
  request: DetectionConfigUpdateRequest
): Promise<DetectionConfig> {
  const response = await fetch(`${API_BASE}/replay/config`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `Failed to update detection config: ${response.statusText}`);
  }
  return response.json();
}

// ============================================================================
// Reference State API (Issue #375 - Reference Layer UI)
// ============================================================================

export interface ReferenceSwing {
  leg_id: string;
  scale: 'S' | 'M' | 'L' | 'XL';
  depth: number;
  location: number;
  salience_score: number;
  direction: 'bull' | 'bear';
  origin_price: number;
  origin_index: number;
  pivot_price: number;
  pivot_index: number;
}

export interface ReferenceStateResponse {
  references: ReferenceSwing[];
  by_scale: {
    S: ReferenceSwing[];
    M: ReferenceSwing[];
    L: ReferenceSwing[];
    XL: ReferenceSwing[];
  };
  by_depth: Record<number, ReferenceSwing[]>;
  by_direction: {
    bull: ReferenceSwing[];
    bear: ReferenceSwing[];
  };
  direction_imbalance: 'bull' | 'bear' | null;
  is_warming_up: boolean;
  warmup_progress: [number, number];
}

export interface ReferenceStateResponseExtended extends ReferenceStateResponse {
  tracked_leg_ids: string[];
}

export async function fetchReferenceState(barIndex?: number): Promise<ReferenceStateResponseExtended> {
  const url = barIndex !== undefined
    ? `${API_BASE}/reference-state?bar_index=${barIndex}`
    : `${API_BASE}/reference-state`;
  const response = await fetch(url);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `Failed to fetch reference state: ${response.statusText}`);
  }
  return response.json();
}

// ============================================================================
// Fib Levels API (Issue #388 - Reference Layer Phase 2)
// ============================================================================

export interface FibLevel {
  price: number;
  ratio: number;
  leg_id: string;
  scale: 'S' | 'M' | 'L' | 'XL';
  direction: 'bull' | 'bear';
}

export interface ActiveLevelsResponse {
  levels_by_ratio: Record<string, FibLevel[]>;
}

export async function fetchActiveLevels(barIndex?: number): Promise<ActiveLevelsResponse> {
  const url = barIndex !== undefined
    ? `${API_BASE}/reference/levels?bar_index=${barIndex}`
    : `${API_BASE}/reference/levels`;
  const response = await fetch(url);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `Failed to fetch active levels: ${response.statusText}`);
  }
  return response.json();
}

export async function trackLegForCrossing(legId: string): Promise<{ success: boolean; leg_id: string; tracked_count: number }> {
  const response = await fetch(`${API_BASE}/reference/track/${encodeURIComponent(legId)}`, {
    method: 'POST',
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `Failed to track leg: ${response.statusText}`);
  }
  return response.json();
}

export async function untrackLegForCrossing(legId: string): Promise<{ success: boolean; leg_id: string; tracked_count: number }> {
  const response = await fetch(`${API_BASE}/reference/track/${encodeURIComponent(legId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `Failed to untrack leg: ${response.statusText}`);
  }
  return response.json();
}
