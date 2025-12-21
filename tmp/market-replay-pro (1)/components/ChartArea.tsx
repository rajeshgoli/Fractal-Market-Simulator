import React, { useEffect, useRef } from 'react';
import { createChart, ColorType, IChartApi, Time } from 'lightweight-charts';
import { ChartDataPoint } from '../types';
import { ChevronDown } from 'lucide-react';

interface ChartAreaProps {
  data1H: ChartDataPoint[];
  data5M: ChartDataPoint[];
}

const ChartHeader: React.FC<{ title: string; timeframe: string }> = ({ title, timeframe }) => (
  <div className="absolute top-2 left-2 z-10 flex items-center gap-2 bg-app-card/80 backdrop-blur border border-app-border rounded px-2 py-1 shadow-sm">
    <span className="text-xs font-bold text-app-text">{title}</span>
    <div className="h-3 w-px bg-app-border"></div>
    <button className="flex items-center gap-1 text-xs text-trading-blue hover:text-blue-400 font-mono">
      {timeframe} <ChevronDown size={10} />
    </button>
  </div>
);

interface SingleChartProps {
  data: ChartDataPoint[];
}

const SingleChart: React.FC<SingleChartProps> = ({ data }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Create Chart
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

    // Add Candlestick Series
    const candlestickSeries = chart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    });

    // Transform Data
    // Lightweight Charts expects time as unix timestamp (seconds) or YYYY-MM-DD string
    const formattedData = data.map(d => ({
        time: new Date(d.time).getTime() / 1000 as Time,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close
    })).sort((a, b) => (a.time as number) - (b.time as number));

    candlestickSeries.setData(formattedData);
    chart.timeScale().fitContent();

    // Resize Handler
    const handleResize = () => {
        if (chartContainerRef.current && chartRef.current) {
            chartRef.current.applyOptions({ 
              width: chartContainerRef.current.clientWidth, 
              height: chartContainerRef.current.clientHeight 
            });
        }
    };

    // Use ResizeObserver for more robust resizing with sidebar toggles
    const resizeObserver = new ResizeObserver(() => handleResize());
    resizeObserver.observe(chartContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [data]);

  return <div ref={chartContainerRef} className="w-full h-full" />;
};

export const ChartArea: React.FC<ChartAreaProps> = ({ data1H, data5M }) => {
  return (
    <div className="flex-1 flex flex-col min-h-0 bg-app-bg">
      {/* Top Chart (1H) */}
      <div className="flex-1 relative border-b border-app-border min-h-0">
        <ChartHeader title="ES_F (S&P 500)" timeframe="1H" />
        <SingleChart data={data1H} />
      </div>

      {/* Bottom Chart (5m) */}
      <div className="flex-1 relative min-h-0">
         <ChartHeader title="ES_F (S&P 500)" timeframe="5m" />
         <SingleChart data={data5M} />
      </div>
    </div>
  );
};