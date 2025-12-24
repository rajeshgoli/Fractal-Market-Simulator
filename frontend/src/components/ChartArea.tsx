import React, { useEffect, useRef } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, CandlestickData, Time, CandlestickSeries, LogicalRange } from 'lightweight-charts';
import { ChevronDown, Maximize2, Minimize2 } from 'lucide-react';
import { BarData, AggregationScale, getFilteredAggregationOptions } from '../types';

interface ChartHeaderProps {
  title: string;
  aggregation: AggregationScale;
  barCount: number;
  onAggregationChange: (scale: AggregationScale) => void;
  isMaximized: boolean;
  onToggleMaximize: () => void;
  sourceResolutionMinutes: number;
}

const ChartHeader: React.FC<ChartHeaderProps> = ({
  title,
  aggregation,
  barCount,
  onAggregationChange,
  isMaximized,
  onToggleMaximize,
  sourceResolutionMinutes
}) => {
  const filteredOptions = getFilteredAggregationOptions(sourceResolutionMinutes);

  return (
    <>
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
            {filteredOptions.map(option => (
              <option key={option.value} value={option.value} className="bg-app-card text-app-text">
                {option.label}
              </option>
            ))}
          </select>
          <ChevronDown size={10} className="absolute right-0 top-1/2 -translate-y-1/2 pointer-events-none text-trading-blue" />
        </div>
      </div>
      <button
        onClick={onToggleMaximize}
        className="absolute top-2 right-2 z-10 p-1.5 bg-app-card/80 backdrop-blur border border-app-border rounded shadow-sm hover:bg-app-card hover:border-trading-blue transition-colors"
        title={isMaximized ? "Restore" : "Maximize"}
      >
        {isMaximized ? (
          <Minimize2 size={14} className="text-app-muted hover:text-trading-blue" />
        ) : (
          <Maximize2 size={14} className="text-app-muted hover:text-trading-blue" />
        )}
      </button>
    </>
  );
};

interface SingleChartProps {
  data: BarData[];
  onChartReady?: (chart: IChartApi, series: ISeriesApi<'Candlestick'>) => void;
  savedZoom?: LogicalRange | null;
  onZoomChange?: (range: LogicalRange | null) => void;
}

const SingleChart: React.FC<SingleChartProps> = ({ data, onChartReady, savedZoom, onZoomChange }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  // Track whether initial data has been loaded (for zoom preservation)
  const hasInitialDataRef = useRef<boolean>(false);
  // Track whether we've applied the saved zoom (only once per mount)
  const hasAppliedSavedZoomRef = useRef<boolean>(false);

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

    // Subscribe to zoom changes for persistence
    const zoomHandler = (range: LogicalRange | null) => {
      if (onZoomChange && hasInitialDataRef.current) {
        onZoomChange(range);
      }
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(zoomHandler);

    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(zoomHandler);
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      hasInitialDataRef.current = false;
      hasAppliedSavedZoomRef.current = false;
    };
  }, [onChartReady, onZoomChange]);

  // Update data when it changes - preserve zoom level (#125)
  useEffect(() => {
    if (seriesRef.current && data.length > 0) {
      // Save current visible range before updating data
      const chart = chartRef.current;
      const currentRange = chart?.timeScale().getVisibleLogicalRange();

      const formattedData: CandlestickData[] = data.map(d => ({
        time: d.timestamp as Time,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      }));
      seriesRef.current.setData(formattedData);

      if (chart) {
        if (!hasInitialDataRef.current) {
          // First time loading data
          hasInitialDataRef.current = true;

          // Try to restore saved zoom from localStorage
          if (savedZoom && !hasAppliedSavedZoomRef.current) {
            hasAppliedSavedZoomRef.current = true;
            // Use requestAnimationFrame to ensure chart is ready
            requestAnimationFrame(() => {
              chart.timeScale().setVisibleLogicalRange(savedZoom);
            });
          } else if (data.length <= 200) {
            // Fit content for small datasets
            chart.timeScale().fitContent();
          }
        } else if (currentRange) {
          // Subsequent updates - restore the saved visible range to preserve zoom
          chart.timeScale().setVisibleLogicalRange(currentRange);
        }
      }
    }
  }, [data, savedZoom]);

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
  sourceResolutionMinutes?: number;
  // Zoom persistence
  chart1Zoom?: LogicalRange | null;
  chart2Zoom?: LogicalRange | null;
  onChart1ZoomChange?: (range: LogicalRange | null) => void;
  onChart2ZoomChange?: (range: LogicalRange | null) => void;
  // Maximized chart state
  maximizedChart?: 1 | 2 | null;
  onMaximizedChartChange?: (value: 1 | 2 | null) => void;
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
  sourceResolutionMinutes = 1,
  chart1Zoom,
  chart2Zoom,
  onChart1ZoomChange,
  onChart2ZoomChange,
  maximizedChart,
  onMaximizedChartChange,
}) => {
  const toggleChart1Maximize = () => {
    onMaximizedChartChange?.(maximizedChart === 1 ? null : 1);
  };

  const toggleChart2Maximize = () => {
    onMaximizedChartChange?.(maximizedChart === 2 ? null : 2);
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-app-bg">
      {/* Top Chart - hidden when chart 2 is maximized */}
      {maximizedChart !== 2 && (
        <div className={`flex-1 relative min-h-0 ${maximizedChart === null ? 'border-b border-app-border' : ''}`}>
          <ChartHeader
            title="Chart 1"
            aggregation={chart1Aggregation}
            barCount={chart1Data.length}
            onAggregationChange={onChart1AggregationChange}
            isMaximized={maximizedChart === 1}
            onToggleMaximize={toggleChart1Maximize}
            sourceResolutionMinutes={sourceResolutionMinutes}
          />
          <SingleChart
            data={chart1Data}
            onChartReady={onChart1Ready}
            savedZoom={chart1Zoom}
            onZoomChange={onChart1ZoomChange}
          />
        </div>
      )}

      {/* Bottom Chart - hidden when chart 1 is maximized */}
      {maximizedChart !== 1 && (
        <div className="flex-1 relative min-h-0">
          <ChartHeader
            title="Chart 2"
            aggregation={chart2Aggregation}
            barCount={chart2Data.length}
            onAggregationChange={onChart2AggregationChange}
            isMaximized={maximizedChart === 2}
            onToggleMaximize={toggleChart2Maximize}
            sourceResolutionMinutes={sourceResolutionMinutes}
          />
          <SingleChart
            data={chart2Data}
            onChartReady={onChart2Ready}
            savedZoom={chart2Zoom}
            onZoomChange={onChart2ZoomChange}
          />
        </div>
      )}
    </div>
  );
};
