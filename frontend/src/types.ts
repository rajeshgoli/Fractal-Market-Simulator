export enum EventType {
  SWING_FORMED = 'SWING_FORMED',
  COMPLETION = 'COMPLETION',
  INVALIDATION = 'INVALIDATION',
  LEVEL_CROSS = 'LEVEL_CROSS',
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

// Playback state machine
export enum PlaybackState {
  STOPPED = 'STOPPED',
  PLAYING = 'PLAYING',
  PAUSED = 'PAUSED',
  LINGERING = 'LINGERING',
}

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

export interface SwingsByDepth {
  depth_1: CalibrationSwing[];  // Root swings (depth 0)
  depth_2: CalibrationSwing[];  // Depth 1
  depth_3: CalibrationSwing[];  // Depth 2
  deeper: CalibrationSwing[];   // Depth 3+
}

export interface TreeStatistics {
  root_swings: number;
  root_bull: number;
  root_bear: number;
  total_nodes: number;
  max_depth: number;
  avg_children: number;
  defended_by_depth: Record<string, number>;
  largest_range: number;
  largest_swing_id: string | null;
  median_range: number;
  smallest_range: number;
  recently_invalidated: number;
  roots_have_children: boolean;
  siblings_detected: boolean;
  no_orphaned_nodes: boolean;
}

export interface CalibrationData {
  calibration_bar_count: number;
  current_price: number;
  tree_stats: TreeStatistics;
  swings_by_depth: SwingsByDepth;
  active_swings_by_depth: SwingsByDepth;
}

// Type alias for backwards compatibility - CalibrationData already has hierarchical tree_stats
export type CalibrationDataHierarchical = CalibrationData;

// Calibration phase states
export enum CalibrationPhase {
  NOT_STARTED = 'NOT_STARTED',
  CALIBRATING = 'CALIBRATING',
  CALIBRATED = 'CALIBRATED',
  PLAYING = 'PLAYING',
}

// ============================================================================
// Swing Display Configuration (Active Swing Count)
// ============================================================================

export const ACTIVE_SWING_COUNT_OPTIONS = [1, 2, 3, 4, 5] as const;

// ============================================================================
// Hierarchical Display Configuration (Issue #166)
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
// DAG State Types (Issue #171 - DAG State Panel)
// ============================================================================

/**
 * Represents an item hovered in the DAG State Panel for chart highlighting.
 */
export interface HighlightedDagItem {
  type: 'leg' | 'pending_origin';
  id: string;  // leg_id or origin key (e.g., "bull-0")
  direction: 'bull' | 'bear';
}

export interface LegEvent {
  type: 'LEG_CREATED' | 'LEG_PRUNED' | 'LEG_INVALIDATED';
  leg_id: string;
  bar_index: number;
  direction: 'bull' | 'bear';
  reason?: string;  // For pruned/invalidated events
  timestamp?: number;  // For display ordering
}

// ============================================================================
// Leg Visualization Types (Issue #172 - DAG View)
// ============================================================================

export type LegStatus = 'active' | 'stale' | 'invalidated';

export interface ActiveLeg {
  leg_id: string;
  direction: 'bull' | 'bear';
  pivot_price: number;
  pivot_index: number;
  origin_price: number;
  origin_index: number;
  retracement_pct: number;
  formed: boolean;
  status: LegStatus;
  bar_count: number;
  // Impulsiveness (0-100): Percentile rank of raw impulse vs all formed legs (#241)
  impulsiveness: number | null;
  // Spikiness (0-100): Sigmoid-normalized skewness of bar contributions (#241)
  spikiness: number | null;
  // Hierarchy fields for exploration (#250, #251)
  parent_leg_id: string | null;
  swing_id: string | null;
  // Segment impulse tracking (#307): Two-impulse model for parent segments
  // impulse_to_deepest: Price change per bar from origin to deepest point
  impulse_to_deepest: number | null;
  // impulse_back: Price change per bar from deepest back to child origin
  impulse_back: number | null;
  // net_segment_impulse: impulse_to_deepest - impulse_back (sustained conviction)
  net_segment_impulse: number | null;
}

// Leg visual style configuration
export const LEG_STATUS_STYLES: Record<LegStatus, {
  lineStyle: 'solid' | 'dashed' | 'dotted';
  opacity: number;
  color: { bull: string; bear: string };
}> = {
  active: {
    lineStyle: 'solid',
    opacity: 0.7,
    color: { bull: '#22C55E', bear: '#EF4444' },  // Green / Red (matches candle colors)
  },
  stale: {
    lineStyle: 'dashed',
    opacity: 0.5,
    color: { bull: '#F59E0B', bear: '#F59E0B' },  // Yellow for both
  },
  invalidated: {
    lineStyle: 'dotted',
    opacity: 0.6,
    color: { bull: '#22C55E', bear: '#EF4444' },  // Same direction colors, dotted
  },
};

// Aggregation scale options - standard timeframes
export const AGGREGATION_OPTIONS = [
  { value: '1m', label: '1m', minutes: 1 },
  { value: '5m', label: '5m', minutes: 5 },
  { value: '15m', label: '15m', minutes: 15 },
  { value: '30m', label: '30m', minutes: 30 },
  { value: '1H', label: '1H', minutes: 60 },
  { value: '4H', label: '4H', minutes: 240 },
  { value: '1D', label: '1D', minutes: 1440 },
] as const;

export type AggregationScale = typeof AGGREGATION_OPTIONS[number]['value'];

/**
 * Get aggregation options filtered by minimum source resolution.
 * Options smaller than the source resolution are excluded.
 */
export function getFilteredAggregationOptions(sourceResolutionMinutes: number) {
  return AGGREGATION_OPTIONS.filter(opt => opt.minutes >= sourceResolutionMinutes);
}

/**
 * Get the smallest valid aggregation scale for a given source resolution.
 * Returns the first option that is >= sourceResolutionMinutes.
 */
export function getSmallestValidAggregation(sourceResolutionMinutes: number): AggregationScale {
  const filtered = getFilteredAggregationOptions(sourceResolutionMinutes);
  return filtered.length > 0 ? filtered[0].value : '1H';
}

/**
 * Clamp an aggregation scale to at least the source resolution.
 * If the current scale is smaller than source resolution, return the smallest valid scale.
 */
export function clampAggregationToSource(scale: AggregationScale, sourceResolutionMinutes: number): AggregationScale {
  const scaleMinutes = getAggregationMinutes(scale);
  if (scaleMinutes >= sourceResolutionMinutes) {
    return scale;
  }
  return getSmallestValidAggregation(sourceResolutionMinutes);
}

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
  return option?.minutes ?? 1;
}

// ============================================================================
// Detection Config Types (Issue #288 - Detection Config UI Panel)
// ============================================================================

/**
 * Per-direction detection configuration.
 */
export interface DirectionConfig {
  formation_fib: number;       // Formation threshold (default: 0.236)
  invalidation_threshold: number;  // Invalidation threshold (default: 0.382)
  engulfed_breach_threshold: number;  // Engulfed threshold (default: 0.0)
}

/**
 * Full detection configuration for swing detection.
 */
export interface DetectionConfig {
  bull: DirectionConfig;
  bear: DirectionConfig;
  stale_extension_threshold: number;  // 3x extension prune (default: 3.0)
  origin_range_threshold: number;  // Origin proximity range threshold (#294)
  origin_time_threshold: number;  // Origin proximity time threshold (#294)
  min_branch_ratio: number;  // Min branch ratio for origin domination (#337, default: 0.0)
  max_legs_per_turn: number;  // Max counter-legs per turn (#340, 0 = disabled)
  // Pruning algorithm toggles
  enable_engulfed_prune: boolean;  // Enable engulfed leg deletion (default: true)
  enable_inner_structure_prune: boolean;  // Enable inner structure pruning (default: false)
}

/**
 * Default detection configuration values.
 */
export const DEFAULT_DETECTION_CONFIG: DetectionConfig = {
  bull: {
    formation_fib: 0.236,
    invalidation_threshold: 0.382,
    engulfed_breach_threshold: 0.0,
  },
  bear: {
    formation_fib: 0.236,
    invalidation_threshold: 0.382,
    engulfed_breach_threshold: 0.0,
  },
  stale_extension_threshold: 3.0,
  origin_range_threshold: 0.0,
  origin_time_threshold: 0.0,
  min_branch_ratio: 0.0,
  max_legs_per_turn: 0,  // Disabled by default
  enable_engulfed_prune: true,
  enable_inner_structure_prune: false,
};
