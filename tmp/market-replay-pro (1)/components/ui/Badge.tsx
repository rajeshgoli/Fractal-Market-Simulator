import React from 'react';
import { Direction } from '../../types';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'outline' | 'bull' | 'bear' | 'neutral';
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({ children, variant = 'default', className = '' }) => {
  let colorClass = 'bg-app-card text-app-text';
  
  switch (variant) {
    case 'bull':
      colorClass = 'bg-trading-bull/20 text-trading-bull border border-trading-bull/30';
      break;
    case 'bear':
      colorClass = 'bg-trading-bear/20 text-trading-bear border border-trading-bear/30';
      break;
    case 'neutral':
      colorClass = 'bg-app-secondary text-app-muted border border-app-border';
      break;
    case 'outline':
      colorClass = 'bg-transparent border border-app-border text-app-muted';
      break;
  }

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded text-xs font-bold uppercase tracking-wider ${colorClass} ${className}`}>
      {children}
    </span>
  );
};