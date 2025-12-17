import React, { useEffect, useRef } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, CandlestickData, Time, CandlestickSeries } from 'lightweight-charts';
import { ChevronDown } from 'lucide-react';
import { BarData, AGGREGATION_OPTIONS, AggregationScale } from '../types';

interface ChartHeaderProps {
  title: string;
  aggregation: AggregationScale;
  barCount: number;
  onAggregationChange: (scale: AggregationScale) => void;
}

const ChartHeader: React.FC<ChartHeaderProps> = ({
  title,
  aggregation,
  barCount,
  onAggregationChange
}) => {
  return (
    <div className="absolute top-2 left-2 z-10 flex items-center gap-2 bg-app-card/80 backdrop-blur border border-app-border rounded px-2 py-1 shadow-sm">
      <span className="text-xs font-bold text-app-text">{title}</span>
      <span className="text-xs text-app-muted">({barCount} bars)</span>
      <div className="h-3 w-px bg-app-border"></div>
      <div className="relative">
        <select
          value={aggregation}
          onChange={(e) => onAggregationChange(e.target.value as AggregationScale)}
          className="appearance-none bg-transparent text-xs text-trading-blue hover:text-blue-400 font-mono pr-4 cursor-pointer focus:outline-none"
        >
          {AGGREGATION_OPTIONS.map(option => (
            <option key={option.value} value={option.value} className="bg-app-card text-app-text">
              {option.label}
            </option>
          ))}
        </select>
        <ChevronDown size={10} className="absolute right-0 top-1/2 -translate-y-1/2 pointer-events-none text-trading-blue" />
      </div>
    </div>
  );
};

interface SingleChartProps {
  data: BarData[];
  onChartReady?: (chart: IChartApi, series: ISeriesApi<'Candlestick'>) => void;
}

const SingleChart: React.FC<SingleChartProps> = ({ data, onChartReady }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#1a1a2e' },
        textColor: '#a0a0a0',
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      },
      grid: {
        vertLines: { color: '#232338' },
        horzLines: { color: '#232338' },
      },
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: '#333333',
      },
      rightPriceScale: {
        borderColor: '#333333',
      },
      crosshair: {
        vertLine: {
          color: '#555',
          labelBackgroundColor: '#555',
        },
        horzLine: {
          color: '#555',
          labelBackgroundColor: '#555',
        },
      },
    });
    chartRef.current = chart;

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    });
    seriesRef.current = candlestickSeries;

    // Notify parent about chart ready
    if (onChartReady) {
      onChartReady(chart, candlestickSeries);
    }

    // Resize Handler using ResizeObserver
    const resizeObserver = new ResizeObserver(() => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight
        });
      }
    });
    resizeObserver.observe(chartContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [onChartReady]);

  // Update data when it changes
  useEffect(() => {
    if (seriesRef.current && data.length > 0) {
      const formattedData: CandlestickData[] = data.map(d => ({
        time: d.timestamp as Time,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      }));
      seriesRef.current.setData(formattedData);

      // Fit content for small datasets, otherwise show last ~100 bars
      if (chartRef.current) {
        if (data.length <= 200) {
          chartRef.current.timeScale().fitContent();
        }
      }
    }
  }, [data]);

  return <div ref={chartContainerRef} className="w-full h-full" />;
};

interface ChartAreaProps {
  chart1Data: BarData[];
  chart2Data: BarData[];
  chart1Aggregation: AggregationScale;
  chart2Aggregation: AggregationScale;
  onChart1AggregationChange: (scale: AggregationScale) => void;
  onChart2AggregationChange: (scale: AggregationScale) => void;
  onChart1Ready?: (chart: IChartApi, series: ISeriesApi<'Candlestick'>) => void;
  onChart2Ready?: (chart: IChartApi, series: ISeriesApi<'Candlestick'>) => void;
}

export const ChartArea: React.FC<ChartAreaProps> = ({
  chart1Data,
  chart2Data,
  chart1Aggregation,
  chart2Aggregation,
  onChart1AggregationChange,
  onChart2AggregationChange,
  onChart1Ready,
  onChart2Ready,
}) => {
  return (
    <div className="flex-1 flex flex-col min-h-0 bg-app-bg">
      {/* Top Chart */}
      <div className="flex-1 relative border-b border-app-border min-h-0">
        <ChartHeader
          title="Chart 1"
          aggregation={chart1Aggregation}
          barCount={chart1Data.length}
          onAggregationChange={onChart1AggregationChange}
        />
        <SingleChart data={chart1Data} onChartReady={onChart1Ready} />
      </div>

      {/* Bottom Chart */}
      <div className="flex-1 relative min-h-0">
        <ChartHeader
          title="Chart 2"
          aggregation={chart2Aggregation}
          barCount={chart2Data.length}
          onAggregationChange={onChart2AggregationChange}
        />
        <SingleChart data={chart2Data} onChartReady={onChart2Ready} />
      </div>
    </div>
  );
};
