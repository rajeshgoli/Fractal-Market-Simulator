import { useEffect, useCallback } from 'react';
import { ISeriesMarkersPluginApi, SeriesMarker, Time } from 'lightweight-charts';
import { DagOrphanedOrigin } from '../lib/api';
import { BarData } from '../types';

interface OrphanedOriginsOverlayProps {
  markersPlugin: ISeriesMarkersPluginApi<Time> | null;
  bullOrigins: DagOrphanedOrigin[];
  bearOrigins: DagOrphanedOrigin[];
  bars: BarData[];
  currentPosition: number;
}

// Marker colors with transparency (30-50% opacity as specified in #182)
const BULL_MARKER_COLOR = 'rgba(59, 130, 246, 0.4)'; // Blue with 40% opacity
const BEAR_MARKER_COLOR = 'rgba(239, 68, 68, 0.4)'; // Red with 40% opacity

/**
 * OrphanedOriginsOverlay renders markers on the chart for orphaned origins.
 *
 * Orphaned origins are preserved pivots from invalidated legs that may form
 * sibling swings. This visualization helps users see where these price levels
 * are in relation to current price action.
 *
 * Visual design:
 * - Bull orphaned origins: Faded blue circles at origin prices
 * - Bear orphaned origins: Faded red circles at origin prices
 * - 40% opacity to distinguish from active legs
 */
export const OrphanedOriginsOverlay: React.FC<OrphanedOriginsOverlayProps> = ({
  markersPlugin,
  bullOrigins,
  bearOrigins,
  bars,
  currentPosition,
}) => {
  // Find bar timestamp by source index
  const getTimestampForIndex = useCallback((barIndex: number): number | null => {
    // Find bar with matching source index range
    for (const bar of bars) {
      if (bar.source_start_index !== undefined && bar.source_end_index !== undefined) {
        if (barIndex >= bar.source_start_index && barIndex <= bar.source_end_index) {
          return bar.timestamp;
        }
      }
      // Fallback: match by exact index
      if (bar.index === barIndex) {
        return bar.timestamp;
      }
    }
    // If not found, try to estimate from bar index
    if (bars.length > 0) {
      const firstBar = bars[0];
      const lastBar = bars[bars.length - 1];
      if (bars.length >= 2) {
        // Estimate timestamp based on linear interpolation
        const barDuration = (lastBar.timestamp - firstBar.timestamp) / (bars.length - 1);
        return firstBar.timestamp + barIndex * barDuration;
      }
    }
    return null;
  }, [bars]);

  // Create markers for origins
  const createMarkers = useCallback((): SeriesMarker<Time>[] => {
    const markers: SeriesMarker<Time>[] = [];

    // Filter origins that are visible (at or before current position)
    const visibleBullOrigins = bullOrigins.filter(o => o.bar_index <= currentPosition);
    const visibleBearOrigins = bearOrigins.filter(o => o.bar_index <= currentPosition);

    // Add bull origin markers (circle below bar)
    for (const origin of visibleBullOrigins) {
      const timestamp = getTimestampForIndex(origin.bar_index);
      if (timestamp !== null) {
        markers.push({
          time: timestamp as Time,
          position: 'aboveBar',
          color: BULL_MARKER_COLOR,
          shape: 'circle',
          text: '',
          size: 1,
        });
      }
    }

    // Add bear origin markers (circle above bar)
    for (const origin of visibleBearOrigins) {
      const timestamp = getTimestampForIndex(origin.bar_index);
      if (timestamp !== null) {
        markers.push({
          time: timestamp as Time,
          position: 'belowBar',
          color: BEAR_MARKER_COLOR,
          shape: 'circle',
          text: '',
          size: 1,
        });
      }
    }

    // Sort by time (required by lightweight-charts)
    markers.sort((a, b) => (a.time as number) - (b.time as number));

    return markers;
  }, [bullOrigins, bearOrigins, currentPosition, getTimestampForIndex]);

  // Update markers when origins or bars change
  useEffect(() => {
    if (!markersPlugin || bars.length === 0) return;

    try {
      const markers = createMarkers();
      markersPlugin.setMarkers(markers);
    } catch (error) {
      console.error('Failed to set orphaned origin markers:', error);
    }

    // Cleanup on unmount
    return () => {
      if (markersPlugin) {
        try {
          markersPlugin.setMarkers([]);
        } catch {
          // Plugin may be disposed
        }
      }
    };
  }, [markersPlugin, bars, createMarkers]);

  // This component doesn't render any DOM elements
  // It only manages markers on the chart via side effects
  return null;
};
