import React, { useRef, useState, useEffect, useCallback } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { ReferenceSwing } from '../lib/api';
import { getBinBadgeColor, formatMedianMultiple } from '../utils/binUtils';

// Constants for layout calculation
const ROW_HEIGHT = 24; // px per row (including padding)
const COLUMN_WIDTH = 140; // px per column
const COLUMN_GAP = 8; // px gap between columns

interface LevelsAtPlayBottomPanelProps {
  references: ReferenceSwing[];
  selectedLegId: string | null;
  hoveredLegId: string | null;
  onHoverLeg: (legId: string | null) => void;
  onSelectLeg: (legId: string) => void;
  isLoading?: boolean;
}

/**
 * LevelsAtPlayBottomPanel displays legs in column-major order.
 *
 * Per #445: Fill columns top-to-bottom, left-to-right.
 * - Most important legs (by salience) appear on the left
 * - Dynamic column count based on available width
 * - Fixed height (no vertical scroll)
 * - Pagination for overflow columns (< prev | next >)
 */
export const LevelsAtPlayBottomPanel: React.FC<LevelsAtPlayBottomPanelProps> = ({
  references,
  selectedLegId,
  hoveredLegId,
  onHoverLeg,
  onSelectLeg,
  isLoading = false,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ rows: 5, visibleCols: 3 });
  const [columnOffset, setColumnOffset] = useState(0);

  // Calculate dimensions based on container size
  const updateDimensions = useCallback(() => {
    if (!containerRef.current) return;

    const rect = containerRef.current.getBoundingClientRect();
    const availableHeight = rect.height - 8; // padding
    const availableWidth = rect.width - 8; // padding

    const rows = Math.max(1, Math.floor(availableHeight / ROW_HEIGHT));
    const visibleCols = Math.max(1, Math.floor((availableWidth + COLUMN_GAP) / (COLUMN_WIDTH + COLUMN_GAP)));

    setDimensions({ rows, visibleCols });
  }, []);

  // Update dimensions on mount and resize
  useEffect(() => {
    updateDimensions();

    const resizeObserver = new ResizeObserver(updateDimensions);
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => resizeObserver.disconnect();
  }, [updateDimensions]);

  // Reset column offset when references change significantly
  useEffect(() => {
    setColumnOffset(0);
  }, [references.length]);

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center text-xs text-app-muted">
        Loading...
      </div>
    );
  }

  if (references.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-xs text-app-muted">
        No active references
      </div>
    );
  }

  const { rows, visibleCols } = dimensions;
  const totalColumns = Math.ceil(references.length / rows);
  const maxColumnOffset = Math.max(0, totalColumns - visibleCols);

  // Get items for current view (column-major order)
  const startCol = columnOffset;
  const endCol = Math.min(startCol + visibleCols, totalColumns);

  // Build columns array for rendering
  const columns: ReferenceSwing[][] = [];
  for (let col = startCol; col < endCol; col++) {
    const columnItems: ReferenceSwing[] = [];
    for (let row = 0; row < rows; row++) {
      const idx = col * rows + row;
      if (idx < references.length) {
        columnItems.push(references[idx]);
      }
    }
    columns.push(columnItems);
  }

  const hasPrev = columnOffset > 0;
  const hasNext = columnOffset < maxColumnOffset;

  return (
    <div ref={containerRef} className="h-full flex flex-col overflow-hidden p-1">
      {/* Column grid - fills available space */}
      <div className="flex-1 flex gap-2 min-h-0">
        {columns.map((columnItems, colIdx) => (
          <div
            key={`col-${startCol + colIdx}`}
            className="flex flex-col gap-0.5"
            style={{ width: COLUMN_WIDTH }}
          >
            {columnItems.map((ref, rowIdx) => {
              const globalIdx = (startCol + colIdx) * rows + rowIdx;
              return (
                <LegItemCompact
                  key={ref.leg_id}
                  reference={ref}
                  rank={globalIdx + 1}
                  isSelected={selectedLegId === ref.leg_id}
                  isHovered={hoveredLegId === ref.leg_id}
                  onHover={onHoverLeg}
                  onClick={onSelectLeg}
                />
              );
            })}
          </div>
        ))}
      </div>

      {/* Pagination - only show if there are hidden columns */}
      {totalColumns > visibleCols && (
        <div className="flex items-center justify-center gap-2 pt-1 shrink-0">
          <button
            onClick={() => setColumnOffset(prev => Math.max(0, prev - 1))}
            disabled={!hasPrev}
            className={`p-0.5 rounded ${hasPrev ? 'hover:bg-app-card text-app-muted hover:text-app-text' : 'text-app-border cursor-not-allowed'}`}
            title="Previous columns"
          >
            <ChevronLeft size={14} />
          </button>
          <span className="text-[10px] text-app-muted">
            {startCol * rows + 1}-{Math.min((endCol) * rows, references.length)} / {references.length}
          </span>
          <button
            onClick={() => setColumnOffset(prev => Math.min(maxColumnOffset, prev + 1))}
            disabled={!hasNext}
            className={`p-0.5 rounded ${hasNext ? 'hover:bg-app-card text-app-muted hover:text-app-text' : 'text-app-border cursor-not-allowed'}`}
            title="Next columns"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
};

interface LegItemCompactProps {
  reference: ReferenceSwing;
  rank: number;
  isSelected: boolean;
  isHovered: boolean;
  onHover: (legId: string | null) => void;
  onClick: (legId: string) => void;
}

const LegItemCompact: React.FC<LegItemCompactProps> = ({
  reference,
  rank,
  isSelected,
  isHovered,
  onHover,
  onClick,
}) => {
  const binStyle = getBinBadgeColor(reference.bin);
  const directionColor = reference.direction === 'bull' ? 'text-trading-bull' : 'text-trading-bear';
  const directionArrow = reference.direction === 'bull' ? '\u25B2' : '\u25BC';
  const medianLabel = formatMedianMultiple(reference.median_multiple);

  // Price display (pivot price is the key level)
  const price = reference.pivot_price.toFixed(2);

  return (
    <div
      className={`flex items-center gap-1 px-1.5 py-1 rounded cursor-pointer transition-colors ${
        isSelected
          ? 'bg-trading-blue/20 ring-1 ring-trading-blue'
          : isHovered
          ? 'bg-app-card/60'
          : 'hover:bg-app-card/40'
      }`}
      onMouseEnter={() => onHover(reference.leg_id)}
      onMouseLeave={() => onHover(null)}
      onClick={() => onClick(reference.leg_id)}
    >
      {/* Rank */}
      <span className="text-[9px] text-app-muted w-4 text-right font-mono shrink-0">
        {rank}.
      </span>

      {/* Bin badge (median multiple) */}
      <span className={`px-1 py-0.5 rounded text-[8px] font-semibold shrink-0 ${binStyle.bg} ${binStyle.text}`}>
        {medianLabel}
      </span>

      {/* Direction arrow */}
      <span className={`text-[9px] shrink-0 ${directionColor}`}>
        {directionArrow}
      </span>

      {/* Price */}
      <span className="text-[9px] font-mono text-app-text truncate">
        {price}
      </span>
    </div>
  );
};
