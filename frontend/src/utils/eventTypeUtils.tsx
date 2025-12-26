/**
 * Event type utilities for icons and colors.
 * Shared logic for displaying event type icons across components.
 */

import React from 'react';
import {
  Activity,
  CheckCircle,
  XCircle,
  Eye,
  GitBranch,
  Scissors,
  Ban,
  AlertTriangle,
} from 'lucide-react';
import { EventType } from '../types';

/**
 * Get the icon component for an event type.
 *
 * @param type - Event type string (EventType enum or legacy string)
 * @param size - Icon size in pixels (default: 16)
 */
export function getIconForEventType(
  type: string,
  size: number = 16
): React.ReactNode {
  switch (type) {
    case EventType.SWING_FORMED:
    case 'SWING_FORMED':
      return <Activity size={size} className="text-trading-purple" />;
    case EventType.COMPLETION:
    case 'SWING_COMPLETED':
      return <CheckCircle size={size} className="text-trading-bull" />;
    case EventType.INVALIDATION:
    case 'SWING_INVALIDATED':
      return <XCircle size={size} className="text-trading-bear" />;
    case EventType.LEVEL_CROSS:
    case 'LEVEL_CROSS':
      return <Eye size={size} className="text-trading-blue" />;
    case 'LEG_CREATED':
      return <GitBranch size={size} className="text-trading-blue" />;
    case 'LEG_PRUNED':
      return <Scissors size={size} className="text-trading-orange" />;
    case 'LEG_INVALIDATED':
      return <Ban size={size} className="text-trading-bear" />;
    default:
      return <AlertTriangle size={size} className="text-trading-orange" />;
  }
}

/**
 * Get the color class for an event type.
 *
 * @param type - Event type string
 */
export function getColorForEventType(type: string): string {
  switch (type) {
    case EventType.SWING_FORMED:
    case 'SWING_FORMED':
      return 'text-trading-purple';
    case EventType.COMPLETION:
    case 'SWING_COMPLETED':
      return 'text-trading-bull';
    case EventType.INVALIDATION:
    case 'SWING_INVALIDATED':
    case 'LEG_INVALIDATED':
      return 'text-trading-bear';
    case EventType.LEVEL_CROSS:
    case 'LEVEL_CROSS':
    case 'LEG_CREATED':
      return 'text-trading-blue';
    case 'LEG_PRUNED':
      return 'text-trading-orange';
    default:
      return 'text-trading-orange';
  }
}
