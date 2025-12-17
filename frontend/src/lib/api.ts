import { BarData, DiscretizationEvent, DiscretizationSwing, AggregationScale, DetectedSwing } from '../types';

const API_BASE = '/api';

export interface SessionInfo {
  session_id: string;
  data_file: string;
  resolution: string;
  window_size: number;
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
