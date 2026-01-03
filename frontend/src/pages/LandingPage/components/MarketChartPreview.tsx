import { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart,
  ColorType,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  Time,
  CandlestickSeries,
  LineSeries,
  LineStyle,
  LineData,
  LineWidth,
} from 'lightweight-charts';

// Pre-baked OHLC data showing clear market structure
// Timestamps are arbitrary but ascending - represents a nice swing pattern
const PREVIEW_OHLC_DATA: CandlestickData<Time>[] = [
  { time: 1700000000 as Time, open: 4400, high: 4410, low: 4395, close: 4405 },
  { time: 1700001800 as Time, open: 4405, high: 4420, low: 4400, close: 4415 },
  { time: 1700003600 as Time, open: 4415, high: 4430, low: 4410, close: 4425 },
  { time: 1700005400 as Time, open: 4425, high: 4445, low: 4420, close: 4440 },
  { time: 1700007200 as Time, open: 4440, high: 4455, low: 4435, close: 4450 }, // Peak 1
  { time: 1700009000 as Time, open: 4450, high: 4455, low: 4430, close: 4435 },
  { time: 1700010800 as Time, open: 4435, high: 4440, low: 4415, close: 4420 },
  { time: 1700012600 as Time, open: 4420, high: 4425, low: 4400, close: 4405 },
  { time: 1700014400 as Time, open: 4405, high: 4410, low: 4385, close: 4390 }, // Trough
  { time: 1700016200 as Time, open: 4390, high: 4410, low: 4385, close: 4405 },
  { time: 1700018000 as Time, open: 4405, high: 4425, low: 4400, close: 4420 },
  { time: 1700019800 as Time, open: 4420, high: 4440, low: 4415, close: 4435 },
  { time: 1700021600 as Time, open: 4435, high: 4455, low: 4430, close: 4450 },
  { time: 1700023400 as Time, open: 4450, high: 4470, low: 4445, close: 4465 },
  { time: 1700025200 as Time, open: 4465, high: 4480, low: 4460, close: 4475 }, // Peak 2
  { time: 1700027000 as Time, open: 4475, high: 4480, low: 4455, close: 4460 },
  { time: 1700028800 as Time, open: 4460, high: 4465, low: 4440, close: 4445 },
  { time: 1700030600 as Time, open: 4445, high: 4450, low: 4425, close: 4430 },
  { time: 1700032400 as Time, open: 4430, high: 4440, low: 4420, close: 4435 },
  { time: 1700034200 as Time, open: 4435, high: 4445, low: 4430, close: 4440 },
];

// Leg definitions showing structure
interface PreviewLeg {
  id: string;
  direction: 'bull' | 'bear';
  originTime: number;
  originPrice: number;
  pivotTime: number;
  pivotPrice: number;
  label: string;
}

const PREVIEW_LEGS: PreviewLeg[] = [
  {
    id: 'bull-1',
    direction: 'bull',
    originTime: 1700000000,
    originPrice: 4400,
    pivotTime: 1700007200,
    pivotPrice: 4455,
    label: 'Bull Leg 1',
  },
  {
    id: 'bear-1',
    direction: 'bear',
    originTime: 1700007200,
    originPrice: 4455,
    pivotTime: 1700014400,
    pivotPrice: 4385,
    label: 'Bear Leg (Retracement)',
  },
  {
    id: 'bull-2',
    direction: 'bull',
    originTime: 1700014400,
    originPrice: 4385,
    pivotTime: 1700025200,
    pivotPrice: 4480,
    label: 'Bull Leg 2 (Extension)',
  },
];

// Fib ratios to display
const FIB_RATIOS = [0.382, 0.618, 1.0, 1.618];

// Compute fib levels for a leg
const computeFibLevels = (leg: PreviewLeg): { ratio: number; price: number }[] => {
  const origin = leg.originPrice;
  const pivot = leg.pivotPrice;

  return FIB_RATIOS.map(ratio => {
    // For fib levels: 0 = origin, 1 = pivot
    // price = origin + ratio * (pivot - origin)
    const price = origin + ratio * (pivot - origin);
    return { ratio, price };
  });
};

export const MarketChartPreview: React.FC = () => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const legSeriesRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map());
  const fibSeriesRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map());

  const [hoveredLeg, setHoveredLeg] = useState<PreviewLeg | null>(null);
  const [isChartReady, setIsChartReady] = useState(false);

  // Get leg pixel positions for hover detection
  const getLegPositions = useCallback(() => {
    if (!chartRef.current || !candleSeriesRef.current) return [];

    const chart = chartRef.current;
    const series = candleSeriesRef.current;
    const timeScale = chart.timeScale();

    return PREVIEW_LEGS.map(leg => {
      const originX = timeScale.timeToCoordinate(leg.originTime as Time);
      const originY = series.priceToCoordinate(leg.originPrice);
      const pivotX = timeScale.timeToCoordinate(leg.pivotTime as Time);
      const pivotY = series.priceToCoordinate(leg.pivotPrice);

      return {
        leg,
        originX: originX ?? 0,
        originY: originY ?? 0,
        pivotX: pivotX ?? 0,
        pivotY: pivotY ?? 0,
      };
    });
  }, []);

  // Distance from point to line segment
  const distanceToLineSegment = (
    px: number, py: number,
    x1: number, y1: number,
    x2: number, y2: number
  ): number => {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const lengthSq = dx * dx + dy * dy;

    if (lengthSq === 0) {
      return Math.sqrt((px - x1) ** 2 + (py - y1) ** 2);
    }

    let t = ((px - x1) * dx + (py - y1) * dy) / lengthSq;
    t = Math.max(0, Math.min(1, t));

    const projX = x1 + t * dx;
    const projY = y1 + t * dy;

    return Math.sqrt((px - projX) ** 2 + (py - projY) ** 2);
  };

  // Find nearest leg to mouse position
  const findNearestLeg = useCallback((x: number, y: number): PreviewLeg | null => {
    const positions = getLegPositions();
    const THRESHOLD = 20; // pixels

    let nearestLeg: PreviewLeg | null = null;
    let nearestDistance = Infinity;

    for (const pos of positions) {
      const distance = distanceToLineSegment(
        x, y,
        pos.originX, pos.originY,
        pos.pivotX, pos.pivotY
      );

      if (distance < nearestDistance && distance <= THRESHOLD) {
        nearestDistance = distance;
        nearestLeg = pos.leg;
      }
    }

    return nearestLeg;
  }, [getLegPositions]);

  // Create leg line series
  const createLegLine = useCallback((
    chart: IChartApi,
    leg: PreviewLeg,
    isHighlighted: boolean
  ): ISeriesApi<'Line'> => {
    const color = leg.direction === 'bull' ? '#22c55e' : '#ef4444';
    const opacity = isHighlighted ? 1.0 : 0.7;
    const lineWidth = isHighlighted ? 3 : 2;

    const r = parseInt(color.slice(1, 3), 16);
    const g = parseInt(color.slice(3, 5), 16);
    const b = parseInt(color.slice(5, 7), 16);

    const lineSeries = chart.addSeries(LineSeries, {
      color: `rgba(${r}, ${g}, ${b}, ${opacity})`,
      lineWidth: lineWidth as LineWidth,
      lineStyle: LineStyle.Solid,
      crosshairMarkerVisible: false,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    const data: LineData<Time>[] = [
      { time: leg.originTime as Time, value: leg.originPrice },
      { time: leg.pivotTime as Time, value: leg.pivotPrice },
    ];
    data.sort((a, b) => (a.time as number) - (b.time as number));

    lineSeries.setData(data);
    return lineSeries;
  }, []);

  // Create fib level lines for a leg
  const createFibLines = useCallback((
    chart: IChartApi,
    leg: PreviewLeg
  ): ISeriesApi<'Line'>[] => {
    const color = leg.direction === 'bull' ? '#22c55e' : '#ef4444';
    const fibLevels = computeFibLevels(leg);
    const series: ISeriesApi<'Line'>[] = [];

    // Get visible time range
    const firstTime = PREVIEW_OHLC_DATA[0].time as number;
    const lastTime = PREVIEW_OHLC_DATA[PREVIEW_OHLC_DATA.length - 1].time as number;

    for (const { price } of fibLevels) {
      const r = parseInt(color.slice(1, 3), 16);
      const g = parseInt(color.slice(3, 5), 16);
      const b = parseInt(color.slice(5, 7), 16);

      const fibSeries = chart.addSeries(LineSeries, {
        color: `rgba(${r}, ${g}, ${b}, 0.4)`,
        lineWidth: 1 as LineWidth,
        lineStyle: LineStyle.Dashed,
        crosshairMarkerVisible: false,
        priceLineVisible: false,
        lastValueVisible: false,
        // Prevent fib lines from affecting auto-scale
        autoscaleInfoProvider: () => null,
      });

      const data: LineData<Time>[] = [
        { time: firstTime as Time, value: price },
        { time: lastTime as Time, value: price },
      ];

      fibSeries.setData(data);
      series.push(fibSeries);
    }

    return series;
  }, []);

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#0f172a' },
        textColor: '#64748b',
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight,
      timeScale: {
        timeVisible: false,
        borderColor: '#334155',
        visible: false, // Hide time scale for cleaner preview
      },
      rightPriceScale: {
        borderColor: '#334155',
        visible: false, // Hide price scale for cleaner preview
      },
      crosshair: {
        vertLine: { visible: false },
        horzLine: { visible: false },
      },
      handleScroll: false,
      handleScale: false,
    });
    chartRef.current = chart;

    // Create candlestick series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    });
    candleSeriesRef.current = candleSeries;
    candleSeries.setData(PREVIEW_OHLC_DATA);

    // Create leg lines
    for (const leg of PREVIEW_LEGS) {
      const lineSeries = createLegLine(chart, leg, false);
      legSeriesRef.current.set(leg.id, lineSeries);
    }

    // Fit content with some padding
    chart.timeScale().fitContent();

    setIsChartReady(true);

    // Resize handler
    const resizeObserver = new ResizeObserver(() => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    });
    resizeObserver.observe(chartContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      legSeriesRef.current.clear();
      fibSeriesRef.current.clear();
      setIsChartReady(false);
    };
  }, [createLegLine]);

  // Update leg highlighting on hover
  useEffect(() => {
    if (!chartRef.current || !isChartReady) return;

    const chart = chartRef.current;

    // Clear existing leg series
    for (const [, series] of legSeriesRef.current) {
      try {
        chart.removeSeries(series);
      } catch {
        // Series may already be removed
      }
    }
    legSeriesRef.current.clear();

    // Clear existing fib series
    for (const [, series] of fibSeriesRef.current) {
      try {
        chart.removeSeries(series);
      } catch {
        // Series may already be removed
      }
    }
    fibSeriesRef.current.clear();

    // Recreate leg lines with proper highlighting
    for (const leg of PREVIEW_LEGS) {
      const isHighlighted = hoveredLeg?.id === leg.id;
      const lineSeries = createLegLine(chart, leg, isHighlighted);
      legSeriesRef.current.set(leg.id, lineSeries);
    }

    // Create fib lines for hovered leg
    if (hoveredLeg) {
      const fibLines = createFibLines(chart, hoveredLeg);
      fibLines.forEach((series, i) => {
        fibSeriesRef.current.set(`${hoveredLeg.id}_fib_${i}`, series);
      });
    }
  }, [hoveredLeg, isChartReady, createLegLine, createFibLines]);

  // Mouse move handler for hover detection
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!chartContainerRef.current || !isChartReady) return;

    const rect = chartContainerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const nearestLeg = findNearestLeg(x, y);
    setHoveredLeg(nearestLeg);
  }, [isChartReady, findNearestLeg]);

  const handleMouseLeave = useCallback(() => {
    setHoveredLeg(null);
  }, []);

  // Compute fib label positions for overlay
  const getFibLabelPositions = useCallback(() => {
    if (!hoveredLeg || !chartRef.current || !candleSeriesRef.current) return [];

    const series = candleSeriesRef.current;
    const fibLevels = computeFibLevels(hoveredLeg);

    return fibLevels.map(({ ratio, price }) => {
      const y = series.priceToCoordinate(price);
      return { ratio, y: y ?? 0 };
    }).filter(p => p.y !== 0);
  }, [hoveredLeg]);

  return (
    <div className="w-full rounded-2xl overflow-hidden shadow-2xl shadow-cyan-500/10 border border-white/10 relative">
      <div
        ref={chartContainerRef}
        className="w-full aspect-[16/9] bg-slate-900"
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      />

      {/* Fib level labels overlay */}
      {hoveredLeg && isChartReady && (
        <div className="absolute inset-0 pointer-events-none">
          {getFibLabelPositions().map(({ ratio, y }) => (
            <div
              key={ratio}
              className="absolute left-2 transform -translate-y-1/2"
              style={{ top: y }}
            >
              <span
                className={`text-xs font-mono px-1.5 py-0.5 rounded ${
                  hoveredLeg.direction === 'bull'
                    ? 'bg-green-500/20 text-green-400'
                    : 'bg-red-500/20 text-red-400'
                }`}
              >
                {ratio.toFixed(3)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Leg info tooltip */}
      {hoveredLeg && (
        <div className="absolute bottom-4 left-4 bg-slate-800/90 backdrop-blur border border-white/10 rounded-lg px-3 py-2 pointer-events-none">
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                hoveredLeg.direction === 'bull' ? 'bg-green-500' : 'bg-red-500'
              }`}
            />
            <span className="text-sm font-medium text-white">{hoveredLeg.label}</span>
          </div>
          <div className="text-xs text-slate-400 mt-1">
            {hoveredLeg.originPrice.toFixed(2)} → {hoveredLeg.pivotPrice.toFixed(2)}
          </div>
        </div>
      )}

      {/* Subtle instruction hint */}
      {!hoveredLeg && isChartReady && (
        <div className="absolute bottom-4 right-4 text-xs text-slate-500 pointer-events-none">
          Hover legs for Fibonacci levels
        </div>
      )}
    </div>
  );
};
