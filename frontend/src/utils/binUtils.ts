/**
 * Bin-based classification utilities for the scale -> bin migration (#436).
 *
 * Bins 0-10 represent ranges of median multiples:
 * - Bins 0-7: Small legs (gray) - below 5x median
 * - Bin 8: Significant (blue) - 5-10x median
 * - Bin 9: Large (purple) - 10-25x median
 * - Bin 10: Exceptional (gold) - 25x+ median
 */

/**
 * Get the display color for a bin value.
 * Returns CSS classes for background and text color.
 */
export function getBinBadgeColor(bin: number): { bg: string; text: string } {
  if (bin <= 7) {
    // Small legs - gray
    return { bg: 'bg-gray-600/20', text: 'text-gray-400' };
  } else if (bin === 8) {
    // Significant - blue
    return { bg: 'bg-blue-600/20', text: 'text-blue-400' };
  } else if (bin === 9) {
    // Large - purple
    return { bg: 'bg-purple-600/20', text: 'text-purple-400' };
  } else {
    // Exceptional (bin 10+) - gold
    return { bg: 'bg-yellow-600/20', text: 'text-yellow-400' };
  }
}

/**
 * Get hex colors for a bin value (for SVG/canvas rendering).
 */
export function getBinHexColors(bin: number): { bg: string; text: string } {
  if (bin <= 7) {
    return { bg: '#4b5563', text: '#9ca3af' };  // gray
  } else if (bin === 8) {
    return { bg: '#2563eb', text: '#60a5fa' };  // blue
  } else if (bin === 9) {
    return { bg: '#9333ea', text: '#c084fc' };  // purple
  } else {
    return { bg: '#ca8a04', text: '#fbbf24' };  // gold
  }
}

/**
 * Format median multiple for display.
 * Examples: 2.5 -> "2.5x", 10 -> "10x", 25.5 -> "25x+"
 *
 * @param medianMultiple The ratio to running median
 * @returns Formatted string like "2.5x" or "25x+"
 */
export function formatMedianMultiple(medianMultiple: number): string {
  if (medianMultiple >= 25) {
    return '25x+';
  } else if (medianMultiple >= 10) {
    return `${Math.round(medianMultiple)}x`;
  } else if (medianMultiple >= 1) {
    return `${medianMultiple.toFixed(1)}x`;
  } else {
    return `${medianMultiple.toFixed(2)}x`;
  }
}

/**
 * Get a human-readable label for a bin range.
 * Examples: bin 6 -> "2-3x", bin 8 -> "5-10x", bin 10 -> "25x+"
 */
export function getBinRangeLabel(bin: number): string {
  // Bin ranges based on median multiple boundaries
  const binRanges: Record<number, string> = {
    0: '<0.25x',
    1: '0.25-0.5x',
    2: '0.5-0.75x',
    3: '0.75-1x',
    4: '1-1.5x',
    5: '1.5-2x',
    6: '2-3x',
    7: '3-5x',
    8: '5-10x',
    9: '10-25x',
    10: '25x+',
  };
  return binRanges[bin] || `bin ${bin}`;
}

/**
 * Get a short label for the bin category.
 */
export function getBinCategoryLabel(bin: number): string {
  if (bin <= 7) {
    return 'Small';
  } else if (bin === 8) {
    return 'Sig';  // Significant
  } else if (bin === 9) {
    return 'Large';
  } else {
    return 'XL';  // Exceptional
  }
}

/**
 * Get line width for chart rendering based on bin.
 */
export function getBinLineWidth(bin: number): 1 | 2 | 3 {
  if (bin <= 7) {
    return 1;
  } else if (bin === 8) {
    return 2;
  } else {
    return 3;
  }
}

/**
 * Get CSS class name for bin-based styling.
 */
export function getBinClassName(bin: number): string {
  if (bin <= 7) {
    return 'bin-small';
  } else if (bin === 8) {
    return 'bin-significant';
  } else if (bin === 9) {
    return 'bin-large';
  } else {
    return 'bin-exceptional';
  }
}
