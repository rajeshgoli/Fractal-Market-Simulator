import { BarData, DiscretizationEvent, DiscretizationSwing, AggregationScale, DetectedSwing, CalibrationData } from '../types';

const API_BASE = '/api';

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

export async function fetchDiscretizationState(): Promise<{
  has_log: boolean;
  event_count: number;
  swing_count: number;
  scales: string[];
}> {
  const response = await fetch(`${API_BASE}/discretization/state`);
  if (!response.ok) {
    throw new Error(`Failed to fetch discretization state: ${response.statusText}`);
  }
  return response.json();
}

export async function runDiscretization(): Promise<{
  success: boolean;
  event_count: number;
  swing_count: number;
  scales_processed: string[];
  message: string;
}> {
  const response = await fetch(`${API_BASE}/discretization/run`, { method: 'POST' });
  if (!response.ok) {
    throw new Error(`Failed to run discretization: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchDiscretizationEvents(): Promise<DiscretizationEvent[]> {
  const response = await fetch(`${API_BASE}/discretization/events`);
  if (!response.ok) {
    throw new Error(`Failed to fetch events: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchDiscretizationSwings(): Promise<DiscretizationSwing[]> {
  const response = await fetch(`${API_BASE}/discretization/swings`);
  if (!response.ok) {
    throw new Error(`Failed to fetch swings: ${response.statusText}`);
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
  type: 'SWING_FORMED' | 'SWING_INVALIDATED' | 'SWING_COMPLETED' | 'LEVEL_CROSS';
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
  event_type: string;
  scale: string;
  swing?: {
    high_bar_index: number;
    low_bar_index: number;
    high_price: string;
    low_price: string;
    direction: string;
  };
  detection_bar_index?: number;
}

export interface PlaybackFeedbackResponse {
  success: boolean;
  observation_id: string;
  message: string;
}

export async function submitPlaybackFeedback(
  text: string,
  playbackBar: number,
  eventContext: PlaybackFeedbackEventContext
): Promise<PlaybackFeedbackResponse> {
  const response = await fetch(`${API_BASE}/playback/feedback`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      text,
      playback_bar: playbackBar,
      event_context: eventContext,
    }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(errorData.detail || `Failed to submit feedback: ${response.statusText}`);
  }
  return response.json();
}
