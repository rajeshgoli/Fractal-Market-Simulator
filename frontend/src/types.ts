export enum EventType {
  SWING_FORMED = 'SWING_FORMED',
  COMPLETION = 'COMPLETION',
  INVALIDATION = 'INVALIDATION',
  LEVEL_CROSS = 'LEVEL_CROSS',
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
  triggerExplanation?: string;
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

// Detected swing for Replay View visualization
export interface DetectedSwing {
  id: string;
  direction: 'bull' | 'bear';
  high_price: number;
  high_bar_index: number;
  low_price: number;
  low_bar_index: number;
  size: number;
  rank: number;
  // Fib levels for overlay
  fib_0: number;    // Defended pivot (0)
  fib_0382: number; // First retracement (0.382)
  fib_1: number;    // Origin extremum (1.0)
  fib_2: number;    // Completion target (2.0)
}

// Swing colors by rank (1-indexed)
export const SWING_COLORS: Record<number, string> = {
  1: '#3B82F6', // Blue (biggest)
  2: '#10B981', // Green
  3: '#F59E0B', // Orange
  4: '#8B5CF6', // Purple
  5: '#EC4899', // Pink
};

// ============================================================================
// Calibration Types (Replay View v2)
// ============================================================================

export interface CalibrationSwing {
  id: string;
  scale: string;
  direction: 'bull' | 'bear';
  high_price: number;
  high_bar_index: number;
  low_price: number;
  low_bar_index: number;
  size: number;
  rank: number;
  is_active: boolean;
  // Fib levels for overlay
  fib_0: number;
  fib_0382: number;
  fib_1: number;
  fib_2: number;
}

export interface CalibrationScaleStats {
  total_swings: number;
  active_swings: number;
}

export interface CalibrationData {
  calibration_bar_count: number;
  current_price: number;
  swings_by_scale: Record<string, CalibrationSwing[]>;
  active_swings_by_scale: Record<string, CalibrationSwing[]>;
  scale_thresholds: Record<string, number>;
  stats_by_scale: Record<string, CalibrationScaleStats>;
}

// Calibration phase states
export enum CalibrationPhase {
  NOT_STARTED = 'NOT_STARTED',
  CALIBRATING = 'CALIBRATING',
  CALIBRATED = 'CALIBRATED',
  PLAYING = 'PLAYING',
}

// ============================================================================
// Swing Display Configuration (Scale Toggles + Active Swing Count)
// ============================================================================

export type SwingScaleKey = 'XL' | 'L' | 'M' | 'S';

// Legacy scale-based config (for backward compatibility)
export interface SwingDisplayConfig {
  enabledScales: Set<SwingScaleKey>;
  activeSwingCount: number;  // 1-5, how many top swings to show per scale
}

export const DEFAULT_SWING_DISPLAY_CONFIG: SwingDisplayConfig = {
  enabledScales: new Set(['XL', 'L', 'M'] as SwingScaleKey[]),  // S off by default
  activeSwingCount: 2,
};

export const ACTIVE_SWING_COUNT_OPTIONS = [1, 2, 3, 4, 5] as const;

// ============================================================================
// Hierarchical Display Configuration (Issue #166 - Replaces Scale)
// ============================================================================

export type DepthFilterKey = 'root_only' | '2_levels' | '3_levels' | 'all';
export type SwingStatusKey = 'defended' | 'completed' | 'invalidated';
export type SwingDirectionKey = 'bull' | 'bear';

export interface HierarchicalDisplayConfig {
  depthFilter: DepthFilterKey;  // How many levels to show
  enabledStatuses: Set<SwingStatusKey>;  // Which statuses to show
  enabledDirections: Set<SwingDirectionKey>;  // Which directions to show
  activeSwingCount: number;  // 1-5, how many largest defended swings to show
}

export const DEFAULT_HIERARCHICAL_DISPLAY_CONFIG: HierarchicalDisplayConfig = {
  depthFilter: 'all',
  enabledStatuses: new Set(['defended', 'completed']),  // invalidated off by default
  enabledDirections: new Set(['bull', 'bear']),
  activeSwingCount: 2,
};

export const DEPTH_FILTER_OPTIONS: { value: DepthFilterKey; label: string }[] = [
  { value: 'root_only', label: 'Root only' },
  { value: '2_levels', label: '2 levels' },
  { value: '3_levels', label: '3 levels' },
  { value: 'all', label: 'All' },
];

// ============================================================================
// Tree Statistics (Issue #166)
// ============================================================================

export interface TreeStatistics {
  root_swings: number;
  root_bull: number;
  root_bear: number;
  total_nodes: number;
  max_depth: number;
  avg_children: number;
  defended_by_depth: Record<string, number>;  // {"1": 12, "2": 38, ...}
  largest_range: number;
  largest_swing_id: string | null;
  median_range: number;
  smallest_range: number;
  recently_invalidated: number;
  roots_have_children: boolean;
  siblings_detected: boolean;
  no_orphaned_nodes: boolean;
}

export interface SwingsByDepth {
  depth_1: CalibrationSwing[];  // Root swings (depth 0)
  depth_2: CalibrationSwing[];  // Depth 1
  depth_3: CalibrationSwing[];  // Depth 2
  deeper: CalibrationSwing[];   // Depth 3+
}

// Extended CalibrationData with hierarchical info
export interface CalibrationDataHierarchical extends CalibrationData {
  tree_stats: TreeStatistics;
  swings_by_depth: SwingsByDepth;
  active_swings_by_depth: SwingsByDepth;
}

// ============================================================================
// DAG State Types (Issue #171 - DAG State Panel)
// ============================================================================

export interface LegEvent {
  type: 'LEG_CREATED' | 'LEG_PRUNED' | 'LEG_INVALIDATED';
  leg_id: string;
  bar_index: number;
  direction: 'bull' | 'bear';
  reason?: string;  // For pruned/invalidated events
  timestamp?: number;  // For display ordering
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
