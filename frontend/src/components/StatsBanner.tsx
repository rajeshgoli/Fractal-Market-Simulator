interface StatsBannerProps {
  className?: string;
}

export const StatsBanner: React.FC<StatsBannerProps> = ({ className = '' }) => {
  const stats = [
    { value: '747', label: 'commits' },
    { value: '37k', label: 'lines' },
    { value: '600+', label: 'tests' },
    { value: '23', label: 'days' },
    { value: '1', label: 'person' },
  ];

  return (
    <div className={`w-full py-6 bg-slate-800 border-y border-slate-700/50 ${className}`}>
      <div className="max-w-7xl mx-auto px-6">
        <div className="flex items-center justify-center gap-3 md:gap-8 flex-wrap">
          {stats.map((stat, i) => (
            <div key={i} className="flex items-center">
              <span className="font-mono font-bold text-white text-sm md:text-base">
                {stat.value}
              </span>
              <span className="ml-1.5 text-slate-400 text-xs md:text-sm">
                {stat.label}
              </span>
              {i < stats.length - 1 && (
                <span className="ml-3 md:ml-8 text-slate-600 hidden sm:inline">•</span>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
