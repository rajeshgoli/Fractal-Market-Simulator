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
];

// Speed multipliers: how many aggregated bars per second at the selected aggregation
// Max 20x since 50ms is the animation floor (1000/20 = 50ms)
export const PLAYBACK_SPEEDS = [
  { value: 1, label: '1x' },
  { value: 2, label: '2x' },
  { value: 5, label: '5x' },
  { value: 10, label: '10x' },
  { value: 20, label: '20x' },
] as const;

export const LINGER_DURATION_MS = 30000; // 30 seconds
