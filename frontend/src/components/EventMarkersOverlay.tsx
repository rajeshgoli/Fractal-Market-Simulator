/**
 * EventMarkersOverlay - Issue #267
 *
 * Displays markers on candles where lifecycle events occurred for followed legs.
 * Uses the lightweight-charts SeriesMarkersPlugin API.
 * Supports click detection for marker interaction.
 */

import { useEffect, useCallback } from 'react';
import { IChartApi, ISeriesApi, ISeriesMarkersPluginApi, Time, SeriesMarker } from 'lightweight-charts';
import { BarData } from '../types';
import { LifecycleEventWithLegInfo } from '../hooks/useFollowLeg';

interface EventMarkersOverlayProps {
  chart: IChartApi | null;
  series: ISeriesApi<'Candlestick'> | null;
  markersPlugin: ISeriesMarkersPluginApi<Time> | null;
  bars: BarData[];
  eventsByBar: Map<number, LifecycleEventWithLegInfo[]>;
  onMarkerClick?: (barIndex: number, events: LifecycleEventWithLegInfo[], position: { x: number; y: number }) => void;
}

/**
 * Get marker shape based on event type
 */
function getMarkerShape(eventType: string): 'arrowUp' | 'arrowDown' | 'circle' | 'square' {
  switch (eventType) {
    case 'formed':
      return 'arrowUp';
    case 'invalidated':
    case 'engulfed':
      return 'arrowDown';
    case 'pruned':
      return 'square';
    case 'origin_breached':
    case 'pivot_breached':
      return 'circle';
    default:
      return 'circle';
  }
}

/**
 * Get marker position based on event
 */
function getMarkerPosition(eventType: string): 'aboveBar' | 'belowBar' {
  // Negative events below, positive events above
  switch (eventType) {
    case 'formed':
      return 'aboveBar';
    case 'invalidated':
    case 'engulfed':
    case 'pruned':
      return 'belowBar';
    case 'origin_breached':
    case 'pivot_breached':
      return 'belowBar';
    default:
      return 'belowBar';
  }
}

/**
 * Get marker text based on event type
 */
function getMarkerText(eventType: string): string {
  switch (eventType) {
    case 'formed':
      return 'F';
    case 'invalidated':
      return 'X';
    case 'engulfed':
      return 'E';
    case 'pruned':
      return 'P';
    case 'origin_breached':
      return 'O!';
    case 'pivot_breached':
      return 'P!';
    default:
      return '?';
  }
}

export const EventMarkersOverlay: React.FC<EventMarkersOverlayProps> = ({
  chart,
  series,
  markersPlugin,
  bars,
  eventsByBar,
  onMarkerClick,
}) => {
  // Build timestamp lookup
  const getTimestampForBarIndex = useCallback((barIndex: number): number | null => {
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
    return null;
  }, [bars]);

  // Update markers when events change
  useEffect(() => {
    if (!markersPlugin || bars.length === 0) {
      return;
    }

    // Build markers from events
    const markers: SeriesMarker<Time>[] = [];

    for (const [barIndex, events] of eventsByBar) {
      const timestamp = getTimestampForBarIndex(barIndex);
      if (timestamp === null) continue;

      // If multiple events on same bar, show the most significant one
      // Priority: invalidated > engulfed > pruned > formed > breaches
      const sortedEvents = [...events].sort((a, b) => {
        const priority: Record<string, number> = {
          invalidated: 5,
          engulfed: 4,
          pruned: 3,
          formed: 2,
          origin_breached: 1,
          pivot_breached: 1,
        };
        return (priority[b.event_type] || 0) - (priority[a.event_type] || 0);
      });

      const primaryEvent = sortedEvents[0];
      const position = getMarkerPosition(primaryEvent.event_type);

      markers.push({
        time: timestamp as Time,
        position,
        color: primaryEvent.legColor,
        shape: getMarkerShape(primaryEvent.event_type),
        text: getMarkerText(primaryEvent.event_type),
        size: events.length > 1 ? 2 : 1, // Larger if multiple events
      });
    }

    // Sort markers by time (required by lightweight-charts)
    markers.sort((a, b) => (a.time as number) - (b.time as number));

    // Update the markers plugin
    markersPlugin.setMarkers(markers);

    // Cleanup: clear markers on unmount
    return () => {
      markersPlugin.setMarkers([]);
    };
  }, [markersPlugin, bars, eventsByBar, getTimestampForBarIndex]);

  // Click handler for marker detection
  useEffect(() => {
    if (!chart || !series || !onMarkerClick || eventsByBar.size === 0) {
      return;
    }

    const chartElement = chart.chartElement();
    if (!chartElement) return;

    const timeScale = chart.timeScale();
    const CLICK_THRESHOLD = 20; // pixels

    const handleClick = (e: MouseEvent) => {
      const rect = chartElement.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const clickY = e.clientY - rect.top;

      // Convert click X to timestamp
      const clickTime = timeScale.coordinateToTime(clickX);
      if (clickTime === null) return;

      // Find the closest marker timestamp
      let closestBarIndex: number | null = null;
      let closestDistance = Infinity;

      for (const [barIndex, events] of eventsByBar) {
        const timestamp = getTimestampForBarIndex(barIndex);
        if (timestamp === null) continue;

        const markerX = timeScale.timeToCoordinate(timestamp as Time);
        if (markerX === null) continue;

        // Get the bar's high/low for Y position calculation
        const bar = bars.find(b =>
          (b.source_start_index !== undefined && barIndex >= b.source_start_index && barIndex <= (b.source_end_index ?? b.source_start_index)) ||
          b.index === barIndex
        );
        if (!bar) continue;

        // Calculate marker Y based on position (above or below bar)
        const primaryEvent = events[0];
        const position = getMarkerPosition(primaryEvent.event_type);
        const markerY = position === 'aboveBar'
          ? series.priceToCoordinate(bar.high)
          : series.priceToCoordinate(bar.low);

        if (markerY === null) continue;

        // Check distance
        const dx = clickX - markerX;
        const dy = clickY - markerY;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance < CLICK_THRESHOLD && distance < closestDistance) {
          closestDistance = distance;
          closestBarIndex = barIndex;
        }
      }

      // If we found a close marker, trigger the callback
      if (closestBarIndex !== null) {
        const events = eventsByBar.get(closestBarIndex);
        if (events) {
          onMarkerClick(closestBarIndex, events, { x: e.clientX, y: e.clientY });
        }
      }
    };

    chartElement.addEventListener('click', handleClick);

    return () => {
      chartElement.removeEventListener('click', handleClick);
    };
  }, [chart, series, onMarkerClick, eventsByBar, bars, getTimestampForBarIndex]);

  // This component only manages markers via the plugin, no visual render
  return null;
};
