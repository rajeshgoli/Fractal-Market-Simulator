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
  id: EventType;
  label: string;
  description: string;
  isEnabled: boolean;
  isDefault?: boolean;
}

export interface SwingData {
  id: string;
  scale: SwingScale;
  direction: Direction;
  highPrice: number;
  highBar: number;
  highTime: string;
  lowPrice: number;
  lowBar: number;
  lowTime: string;
  size: number;
  sizePct: number;
  ratio?: number;
  previousSwingId?: string;
  // Detailed context for advanced explanations
  fibContext?: {
    ratio: number;
    parentHigh: number;
    parentLow: number;
    interveningLow: number;
    innerHigh: number;
  };
}

export interface ChartDataPoint {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}