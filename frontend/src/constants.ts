import { FilterState, EventType } from './types';

export const INITIAL_FILTERS: FilterState[] = [
  {
    id: EventType.SWING_FORMED,
    label: 'Swing Formed',
    description: 'New market structure swing detected',
    isEnabled: true,
    isDefault: true
  },
  {
    id: EventType.COMPLETION,
    label: 'Completion',
    description: 'Ratio reached 2.0 extension',
    isEnabled: true,
    isDefault: true
  },
  {
    id: EventType.INVALIDATION,
    label: 'Invalidation',
    description: 'Ratio dropped below threshold',
    isEnabled: true,
    isDefault: true
  },
  {
    id: EventType.LEVEL_CROSS,
    label: 'Level Cross',
    description: 'Price crossed key Fib level (off by default - too frequent)',
    isEnabled: false
  },
];

// Speed multipliers: how many aggregated bars per second at the selected aggregation
export const PLAYBACK_SPEEDS = [
  { value: 1, label: '1x' },
  { value: 2, label: '2x' },
  { value: 5, label: '5x' },
  { value: 10, label: '10x' },
  { value: 20, label: '20x' },
  { value: 50, label: '50x' },
  { value: 100, label: '100x' },
] as const;

export const LINGER_DURATION_MS = 30000; // 30 seconds
