export enum EventType {
  SWING_FORMED = 'SWING_FORMED',
  COMPLETION = 'COMPLETION',
  INVALIDATION = 'INVALIDATION',
  LEVEL_CROSS = 'LEVEL_CROSS',
  SWING_TERMINATED = 'SWING_TERMINATED',
}

export enum SwingScale {
  S = 'S',
  M = 'M',
  L = 'L',
  XL = 'XL',
}

export enum Direction {
  BULL = 'BULL',
  BEAR = 'BEAR',
}

export interface MarketEvent {
  id: string;
  type: EventType;
  timestamp: string;
  barIndex: number;
  description: string;
}

export interface FilterState {
  id: string;
  label: string;
  description: string;
  isEnabled: boolean;
  isDefault?: boolean;
}

export interface SwingData {
  id: string;
  scale: string;
  direction: string;
  highPrice: number;
  highBar: number;
  highTime: string;
  lowPrice: number;
  lowBar: number;
  lowTime: string;
  size: number;
  sizePct: number;
  scaleReason?: string;
  isAnchor?: boolean;
  separation?: {
    distanceFib: number;
    minimumFib: number;
    fromSwingId: string;
  };
  previousSwingId?: string;
}

export interface ChartDataPoint {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface BarData {
  index: number;
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  source_start_index: number;
  source_end_index: number;
}

export interface DiscretizationEvent {
  bar: number;
  timestamp: string;
  swing_id: string;
  event_type: string;
  data: {
    scale?: string;
    direction?: string;
    explanation?: {
      high?: { price: number; bar: number; timestamp: string };
      low?: { price: number; bar: number; timestamp: string };
      size_pts?: number;
      size_pct?: number;
      scale_reason?: string;
      is_anchor?: boolean;
      separation?: {
        distance_fib: number;
        minimum_fib: number;
        from_swing_id: string;
      };
    };
  };
}

export interface DiscretizationSwing {
  swing_id: string;
  scale: string;
  direction: string;
  anchor0: number;
  anchor1: number;
  anchor0_bar: number;
  anchor1_bar: number;
  formed_at_bar: number;
  status: string;
  terminated_at_bar?: number;
  termination_reason?: string;
}

// Playback state machine
export enum PlaybackState {
  STOPPED = 'STOPPED',
  PLAYING = 'PLAYING',
  PAUSED = 'PAUSED',
  LINGERING = 'LINGERING',
}

// Aggregation scale options (timeframes not S/M/L/XL)
export const AGGREGATION_OPTIONS = [
  { value: 'S', label: '5m', minutes: 5 },
  { value: 'M', label: '15m', minutes: 15 },
  { value: 'L', label: '1H', minutes: 60 },
  { value: 'XL', label: '4H', minutes: 240 },
] as const;

export type AggregationScale = typeof AGGREGATION_OPTIONS[number]['value'];

/**
 * Parse a resolution string (e.g., "5m", "1h", "1D") into minutes.
 */
export function parseResolutionToMinutes(resolution: string): number {
  const match = resolution.match(/^(\d+)([mhDWM])$/i);
  if (!match) {
    console.warn(`Unknown resolution format: ${resolution}, defaulting to 1m`);
    return 1;
  }

  const value = parseInt(match[1], 10);
  const unit = match[2].toLowerCase();

  switch (unit) {
    case 'm': return value;
    case 'h': return value * 60;
    case 'd': return value * 60 * 24;
    case 'w': return value * 60 * 24 * 7;
    default: return value;
  }
}

/**
 * Get the label for an aggregation scale.
 */
export function getAggregationLabel(scale: AggregationScale): string {
  const option = AGGREGATION_OPTIONS.find(o => o.value === scale);
  return option?.label ?? scale;
}

/**
 * Get minutes for an aggregation scale.
 */
export function getAggregationMinutes(scale: AggregationScale): number {
  const option = AGGREGATION_OPTIONS.find(o => o.value === scale);
  return option?.minutes ?? 5;
}
