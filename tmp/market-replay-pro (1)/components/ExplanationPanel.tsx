import React from 'react';
import { SwingData, Direction } from '../types';
import { Badge } from './ui/Badge';
import { Info, ArrowRight, TrendingUp, TrendingDown, GitCommit, Target, Ruler, Layers, Eye } from 'lucide-react';

interface ExplanationPanelProps {
  swing: SwingData | null;
}

export const ExplanationPanel: React.FC<ExplanationPanelProps> = ({ swing }) => {
  if (!swing) {
    return (
      <div className="h-full w-full flex flex-col items-center justify-center text-app-muted border-t border-app-border bg-app-secondary p-6">
        <Info className="w-8 h-8 mb-2 opacity-50" />
        <p>No active swing event selected. Advance playback to see detection details.</p>
      </div>
    );
  }

  const isBull = swing.direction === Direction.BULL;
  const priceColor = isBull ? 'text-trading-bull' : 'text-trading-bear';

  return (
    <div className="h-full bg-app-secondary border-t border-app-border flex flex-col font-sans text-sm">
      {/* Panel Header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-app-border bg-app-bg/40">
        <div className="flex items-center gap-2 text-app-text font-semibold tracking-wider uppercase">
           <GitCommit size={16} className="text-trading-purple" />
           <span>Swing Formed</span>
        </div>
        <div className="h-4 w-px bg-app-border mx-2"></div>
        <div className="flex gap-2">
           <Badge variant="neutral" className="min-w-[2rem] justify-center">{swing.scale}</Badge>
           <Badge variant={isBull ? 'bull' : 'bear'}>{swing.direction}</Badge>
        </div>
      </div>

      {/* Content Grid */}
      <div className="flex-1 grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-app-border/50 overflow-hidden">
        
        {/* Column 1: Endpoints */}
        <div className="p-4 flex flex-col justify-center space-y-4">
          <div className="space-y-3">
            {/* High Point */}
            <div className="flex flex-col">
              <div className="flex justify-between items-end mb-1">
                <span className="text-xs text-app-muted font-medium uppercase tracking-wider">High</span>
                <span className="font-mono text-[10px] text-app-muted bg-app-card px-1.5 py-0.5 rounded border border-app-border/50">
                  Bar {swing.highBar}
                </span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-lg font-mono tabular-nums text-app-text tracking-tight">{swing.highPrice.toFixed(2)}</span>
                <span className="text-xs text-app-muted tabular-nums">{swing.highTime}</span>
              </div>
            </div>

            <div className="h-px bg-app-border/30 w-full"></div>

            {/* Low Point */}
            <div className="flex flex-col">
               <div className="flex justify-between items-end mb-1">
                <span className="text-xs text-app-muted font-medium uppercase tracking-wider">Low</span>
                <span className="font-mono text-[10px] text-app-muted bg-app-card px-1.5 py-0.5 rounded border border-app-border/50">
                  Bar {swing.lowBar}
                </span>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-lg font-mono tabular-nums text-app-text tracking-tight">{swing.lowPrice.toFixed(2)}</span>
                <span className="text-xs text-app-muted tabular-nums">{swing.lowTime}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Column 2: Size & Logic */}
        <div className="p-4 flex flex-col justify-center space-y-4">
          <div>
            <span className="text-xs text-app-muted font-medium uppercase tracking-wider block mb-2">Size & Scale</span>
            <div className="flex items-baseline gap-3">
               <span className={`text-2xl font-mono tabular-nums font-medium ${priceColor}`}>
                 {swing.size.toFixed(2)} <span className="text-sm text-app-muted font-sans">pts</span>
               </span>
               <span className="text-sm text-app-muted tabular-nums">
                 ({swing.sizePct.toFixed(2)}%)
               </span>
            </div>
          </div>

          <div className="bg-app-card/30 rounded border border-app-border/50 p-3">
            <div className="flex items-center gap-2 mb-1.5">
              <Target size={14} className="text-trading-blue" />
              <span className="text-xs font-bold text-app-text">Why {swing.scale}?</span>
            </div>
            <ul className="text-xs text-app-muted space-y-1 ml-1">
              <li className="flex items-start gap-1.5">
                <span className="block w-1 h-1 rounded-full bg-app-border mt-1.5"></span>
                <span>Size &ge; 100 threshold</span>
              </li>
              <li className="flex items-start gap-1.5">
                <span className="block w-1 h-1 rounded-full bg-app-border mt-1.5"></span>
                <span>Valid fib retracement confirmed</span>
              </li>
            </ul>
          </div>
        </div>

        {/* Column 3: Context / Analysis */}
        <div className="p-4 flex flex-col justify-center space-y-4">
          {swing.fibContext ? (
             <div className="space-y-3">
                <div className="flex items-center gap-2 text-xs text-app-muted font-medium uppercase tracking-wider">
                  <Layers size={14} />
                  <span>Market Structure</span>
                </div>
                
                <div className="text-xs text-app-muted leading-relaxed">
                  <p className="mb-2">
                    Matching FIB levels of a bigger swing are: <span className="text-trading-blue font-bold tabular-nums">{swing.fibContext.ratio}</span> for swing from{' '}
                    <span className="text-app-text font-mono tabular-nums">{swing.fibContext.parentHigh}</span> to{' '}
                    <span className="text-app-text font-mono tabular-nums">{swing.fibContext.parentLow}</span>.
                  </p>
                  
                  <div className="pl-2 border-l-2 border-app-border/50 space-y-1 mt-2">
                    <div className="flex justify-between">
                      <span>Intervening low:</span>
                      <span className="text-app-text font-mono tabular-nums">{swing.fibContext.interveningLow}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Inner high:</span>
                      <span className="text-app-text font-mono tabular-nums">{swing.fibContext.innerHigh}</span>
                    </div>
                  </div>

                  <div className="mt-3 flex items-center gap-1.5 text-trading-orange/80 text-[10px] uppercase font-bold tracking-wide">
                     <Eye size={12} />
                     Highlighted on chart
                  </div>
                </div>
             </div>
          ) : (
            <div className="space-y-3">
              <span className="text-xs text-app-muted font-medium uppercase tracking-wider block">Separation</span>
              
              <div>
                <div className="flex justify-between text-xs mb-1.5">
                  <span className="text-app-muted">Fibo Distance</span>
                  <span className="font-mono text-app-text">{swing.ratio}</span>
                </div>
                <div className="relative h-2 bg-app-bg rounded-full overflow-hidden border border-app-border/50">
                   {/* Marker for min req */}
                   <div className="absolute top-0 bottom-0 w-0.5 bg-app-muted/30 z-10" style={{ left: '23.6%' }}></div>
                   {/* Fill */}
                   <div className="absolute top-0 left-0 bottom-0 bg-trading-purple" style={{ width: '42%' }}></div>
                </div>
                <div className="flex justify-between text-[10px] text-app-muted mt-1">
                  <span>0.0</span>
                  <span>Min: 0.236</span>
                  <span>1.0</span>
                </div>
              </div>

              {swing.previousSwingId && (
                <div className="mt-2 pt-3 border-t border-app-border/30">
                  <div className="flex items-center gap-2 text-xs text-app-muted mb-1">
                    <Ruler size={12} />
                    <span>Reference Swing</span>
                  </div>
                  <div className="flex items-center gap-2 text-app-muted/70 text-xs">
                     <ArrowRight size={12} />
                     <code className="bg-app-bg px-1 rounded border border-app-border/50">{swing.previousSwingId}</code>
                     <span className="italic opacity-50">(Dimmed on chart)</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

      </div>
    </div>
  );
};