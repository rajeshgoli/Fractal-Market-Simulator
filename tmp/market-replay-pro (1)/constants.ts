import { FilterState, EventType, SwingScale, Direction, SwingData, ChartDataPoint } from './types';

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
    description: 'Price crossed key Fib level', 
    isEnabled: false 
  },
  { 
    id: EventType.SWING_TERMINATED, 
    label: 'Swing Terminated', 
    description: 'Swing ended logic', 
    isEnabled: false 
  },
];

export const MOCK_SWING: SwingData = {
  id: 'swing-1234',
  scale: SwingScale.XL,
  direction: Direction.BULL,
  highPrice: 5862.50,
  highBar: 1234,
  highTime: 'Mar 15, 14:30',
  lowPrice: 5750.00,
  lowBar: 1200,
  lowTime: 'Mar 14, 09:15',
  size: 112.50,
  sizePct: 1.92,
  ratio: 0.42,
  previousSwingId: 'abc-prev-99',
  fibContext: {
    ratio: 0.287,
    parentHigh: 7754,
    parentLow: 1245,
    interveningLow: 6456,
    innerHigh: 6564
  }
};

// Generate some fake candle data
export const generateChartData = (count: number): ChartDataPoint[] => {
  const data: ChartDataPoint[] = [];
  let price = 5800;
  const now = new Date();
  
  for (let i = 0; i < count; i++) {
    const time = new Date(now.getTime() - (count - i) * 60000 * 60); // 1 hour steps
    const volatility = Math.random() * 20;
    const change = (Math.random() - 0.5) * volatility;
    
    const open = price;
    const close = price + change;
    const high = Math.max(open, close) + Math.random() * 5;
    const low = Math.min(open, close) - Math.random() * 5;
    
    data.push({
      time: time.toISOString(),
      open,
      high,
      low,
      close
    });
    price = close;
  }
  return data;
};

export const MOCK_CHART_DATA_1H = generateChartData(100);
export const MOCK_CHART_DATA_5M = generateChartData(50);
