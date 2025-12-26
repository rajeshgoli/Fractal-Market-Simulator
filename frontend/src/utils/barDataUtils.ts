/**
 * Bar data transformation utilities.
 * Shared logic for converting ReplayBarData to BarData.
 */

import { BarData } from '../types';
import { ReplayBarData } from '../lib/api';

/**
 * Convert a ReplayBarData (from API response) to BarData (for chart display).
 *
 * Note: source_start_index and source_end_index are set to the bar's index
 * since ReplayBarData represents a single source bar, not an aggregated bar.
 */
export function formatReplayBarData(bar: ReplayBarData): BarData {
  return {
    index: bar.index,
    timestamp: bar.timestamp,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
    source_start_index: bar.index,
    source_end_index: bar.index,
  };
}

/**
 * Convert an array of ReplayBarData to BarData[].
 */
export function formatReplayBarsData(bars: ReplayBarData[]): BarData[] {
  return bars.map(formatReplayBarData);
}
