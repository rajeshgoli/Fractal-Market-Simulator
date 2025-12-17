import React from 'react';
import clsx from 'clsx';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'outline' | 'bull' | 'bear' | 'neutral';
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({ children, variant = 'default', className = '' }) => {
  const colorClass = {
    default: 'bg-app-card text-app-text',
    bull: 'bg-trading-bull/20 text-trading-bull border border-trading-bull/30',
    bear: 'bg-trading-bear/20 text-trading-bear border border-trading-bear/30',
    neutral: 'bg-app-secondary text-app-muted border border-app-border',
    outline: 'bg-transparent border border-app-border text-app-muted',
  }[variant];

  return (
    <span className={clsx(
      'inline-flex items-center px-2.5 py-0.5 rounded text-xs font-bold uppercase tracking-wider',
      colorClass,
      className
    )}>
      {children}
    </span>
  );
};
