import React, { useLayoutEffect, useState } from 'react';
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { ReferenceSwing } from '../lib/api';
import { BarData } from '../types';

interface ReferenceLegOverlayProps {
  chart: IChartApi | null;
  series: ISeriesApi<'Candlestick'> | null;
  references: ReferenceSwing[];
  fadingRefs: Set<string>;
  bars: BarData[];
}

interface LegPosition {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  ref: ReferenceSwing;
  isFading: boolean;
}

export const ReferenceLegOverlay: React.FC<ReferenceLegOverlayProps> = ({
  chart,
  series,
  references,
  fadingRefs,
  bars,
}) => {
  const [legPositions, setLegPositions] = useState<LegPosition[]>([]);
  const [chartSize, setChartSize] = useState({ width: 0, height: 0 });

  // Update chart size on resize
  useLayoutEffect(() => {
    if (!chart) return;

    const updateSize = () => {
      const container = chart.chartElement().closest('.chart-container');
      if (container) {
        setChartSize({
          width: container.clientWidth,
          height: container.clientHeight,
        });
      }
    };

    updateSize();

    const observer = new ResizeObserver(updateSize);
    const container = chart.chartElement().closest('.chart-container');
    if (container) {
      observer.observe(container);
    }

    return () => observer.disconnect();
  }, [chart]);

  // Calculate leg positions
  useLayoutEffect(() => {
    if (!chart || !series || bars.length === 0) {
      setLegPositions([]);
      return;
    }

    const calculatePositions = () => {
      const positions: LegPosition[] = [];

      for (const ref of references) {
        // Find bar indices for origin and pivot
        const originBar = bars.find(b =>
          b.source_start_index <= ref.origin_index && b.source_end_index >= ref.origin_index
        );
        const pivotBar = bars.find(b =>
          b.source_start_index <= ref.pivot_index && b.source_end_index >= ref.pivot_index
        );

        if (!originBar || !pivotBar) continue;

        // Get pixel coordinates
        const originX = chart.timeScale().timeToCoordinate(originBar.timestamp as Time);
        const pivotX = chart.timeScale().timeToCoordinate(pivotBar.timestamp as Time);
        const originY = series.priceToCoordinate(ref.origin_price);
        const pivotY = series.priceToCoordinate(ref.pivot_price);

        if (originX === null || pivotX === null || originY === null || pivotY === null) continue;

        positions.push({
          x1: originX,
          y1: originY,
          x2: pivotX,
          y2: pivotY,
          ref,
          isFading: fadingRefs.has(ref.leg_id),
        });
      }

      setLegPositions(positions);
    };

    calculatePositions();

    // Subscribe to chart updates
    chart.timeScale().subscribeVisibleLogicalRangeChange(calculatePositions);

    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(calculatePositions);
    };
  }, [chart, series, references, fadingRefs, bars, chartSize]);

  if (!chart || legPositions.length === 0) {
    return null;
  }

  return (
    <svg
      className="absolute inset-0 pointer-events-none"
      style={{ width: '100%', height: '100%', zIndex: 100 }}
    >
      {legPositions.map((pos) => (
        <LegLine key={pos.ref.leg_id} position={pos} />
      ))}
    </svg>
  );
};

interface LegLineProps {
  position: LegPosition;
}

const LegLine: React.FC<LegLineProps> = ({ position }) => {
  const { x1, y1, x2, y2, ref, isFading } = position;

  // Direction determines color
  // Bull reference (bear leg) = green (price went down, looking to go long)
  // Bear reference (bull leg) = red (price went up, looking to go short)
  const color = ref.direction === 'bear' ? '#22c55e' : '#ef4444';
  const bgColor = ref.direction === 'bear' ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)';

  // Scale determines line thickness
  const strokeWidth = ref.scale === 'XL' ? 3 : ref.scale === 'L' ? 2.5 : ref.scale === 'M' ? 2 : 1.5;

  // Calculate label position (near the pivot point)
  const labelX = x2 + 8;
  const labelY = y2;

  // Scale badge colors
  const getScaleBadgeColor = () => {
    switch (ref.scale) {
      case 'XL': return { bg: '#9333ea', text: '#ffffff' };
      case 'L': return { bg: '#2563eb', text: '#ffffff' };
      case 'M': return { bg: '#16a34a', text: '#ffffff' };
      case 'S': return { bg: '#6b7280', text: '#ffffff' };
      default: return { bg: '#6b7280', text: '#ffffff' };
    }
  };

  const scaleBadge = getScaleBadgeColor();

  return (
    <g
      className={`transition-opacity duration-300 ${isFading ? 'opacity-0' : 'opacity-100'}`}
    >
      {/* Leg line */}
      <line
        x1={x1}
        y1={y1}
        x2={x2}
        y2={y2}
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        opacity={0.8}
      />

      {/* Origin marker (circle) */}
      <circle
        cx={x1}
        cy={y1}
        r={4}
        fill={color}
        opacity={0.8}
      />

      {/* Pivot marker (filled circle with border) */}
      <circle
        cx={x2}
        cy={y2}
        r={5}
        fill={bgColor}
        stroke={color}
        strokeWidth={2}
      />

      {/* Label group */}
      <g transform={`translate(${labelX}, ${labelY})`}>
        {/* Scale badge */}
        <rect
          x={0}
          y={-10}
          width={22}
          height={16}
          rx={3}
          fill={scaleBadge.bg}
        />
        <text
          x={11}
          y={2}
          textAnchor="middle"
          fill={scaleBadge.text}
          fontSize={10}
          fontWeight="600"
          fontFamily="system-ui, sans-serif"
        >
          {ref.scale}
        </text>

        {/* Location indicator */}
        <rect
          x={26}
          y={-10}
          width={32}
          height={16}
          rx={3}
          fill="rgba(30, 41, 59, 0.9)"
          stroke={color}
          strokeWidth={1}
        />
        <text
          x={42}
          y={2}
          textAnchor="middle"
          fill={color}
          fontSize={9}
          fontWeight="500"
          fontFamily="system-ui, sans-serif"
        >
          {ref.location.toFixed(2)}
        </text>
      </g>
    </g>
  );
};
