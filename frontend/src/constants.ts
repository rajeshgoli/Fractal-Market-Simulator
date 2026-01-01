import { FilterState, EventType } from './types';

export const INITIAL_FILTERS: FilterState[] = [
  {
    id: EventType.LEG_CREATED,
    label: 'Leg Created',
    description: 'New leg detected',
    isEnabled: true,
    isDefault: true
  },
  {
    id: EventType.LEG_PRUNED,
    label: 'Leg Pruned',
    description: 'Leg pruned due to threshold',
    isEnabled: true,
    isDefault: true
  },
  {
    id: EventType.LEG_INVALIDATED,
    label: 'Leg Invalidated',
    description: 'Leg invalidated by origin breach',
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
