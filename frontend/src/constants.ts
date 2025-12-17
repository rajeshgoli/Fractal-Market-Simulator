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
  {
    id: EventType.SWING_TERMINATED,
    label: 'Swing Terminated',
    description: 'Swing ended logic (off by default - redundant)',
    isEnabled: false
  },
];

export const PLAYBACK_SPEEDS = [
  { value: 2000, label: '0.5x' },
  { value: 1000, label: '1x' },
  { value: 500, label: '2x' },
  { value: 200, label: '5x' },
  { value: 100, label: '10x' },
] as const;

export const LINGER_DURATION_MS = 30000; // 30 seconds
