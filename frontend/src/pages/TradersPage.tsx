import { Navbar } from './LandingPage/components/Navbar';
import { Footer } from '../components/Footer';
import { MarketChartPreview } from './LandingPage/components/MarketChartPreview';

export const TradersPage: React.FC = () => {
  const handleLogin = async () => {
    try {
      const res = await fetch('/auth/status');
      const data = await res.json();
      if (data.multi_tenant) {
        window.location.href = '/login';
      } else {
        window.location.href = '/app';
      }
    } catch {
      window.location.href = '/app';
    }
  };

  const fibLevels = [
    { level: '0.382', name: 'Shallow Retracement', copy: 'Strong trend continuation zone', color: 'text-green-400' },
    { level: '0.618', name: 'Golden Ratio', copy: 'Key reversal zone', color: 'text-yellow-400' },
    { level: '1.000', name: 'Full Retracement', copy: 'Trend exhaustion', color: 'text-slate-400' },
    { level: '1.618', name: 'Extension', copy: 'Profit targets beyond the swing', color: 'text-cyan-400' },
  ];

  return (
    <div className="min-h-screen fractal-bg">
      <Navbar onLogin={handleLogin} />

      {/* Hero Section */}
      <section className="relative pt-32 pb-20 px-6 overflow-hidden">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-7xl h-full -z-10">
          <div className="absolute top-[10%] left-[10%] w-[500px] h-[500px] bg-cyan-500/10 rounded-full blur-[120px] animate-pulse"></div>
          <div className="absolute bottom-[20%] right-[10%] w-[400px] h-[400px] bg-blue-600/10 rounded-full blur-[100px]"></div>
        </div>

        <div className="max-w-4xl mx-auto text-center mb-12">
          <h1 className="text-5xl md:text-7xl font-black mb-6 tracking-tighter leading-none text-white">
            Find Structure
            <br />
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 via-white to-blue-500">
              Before Price Does
            </span>
          </h1>

          <p className="text-lg md:text-xl text-slate-400 leading-relaxed max-w-2xl mx-auto">
            Hierarchical swing detection with Fibonacci levels. No lookahead. No curve fitting. The system identifies decision points before price arrives.
          </p>
        </div>

        {/* Chart Preview */}
        <div className="max-w-5xl mx-auto">
          <MarketChartPreview />
        </div>
      </section>

      {/* How It Works Section */}
      <section className="py-20 px-6 bg-slate-950/50">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-white text-center mb-4">Three Steps to Structure</h2>
          <p className="text-slate-400 text-center mb-12">How the algorithm finds decision points</p>

          <div className="grid md:grid-cols-3 gap-8">
            {/* Step 1 */}
            <div className="glass p-8 rounded-xl text-center">
              <div className="w-16 h-16 mx-auto mb-6 bg-slate-800 rounded-xl flex items-center justify-center">
                <svg className="w-10 h-10 text-cyan-400" viewBox="0 0 100 60" fill="none" stroke="currentColor" strokeWidth="3">
                  <polyline points="10,50 30,20 50,40 70,10 90,30" />
                </svg>
              </div>
              <h3 className="text-xl font-bold text-white mb-3">Detect Swings</h3>
              <p className="text-slate-400">Identify the skeleton underneath price action</p>
            </div>

            {/* Arrow */}
            <div className="hidden md:flex items-center justify-center">
              <svg className="w-8 h-8 text-slate-600 -mt-20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>

            {/* Step 2 */}
            <div className="glass p-8 rounded-xl text-center md:col-start-2">
              <div className="w-16 h-16 mx-auto mb-6 bg-slate-800 rounded-xl flex items-center justify-center relative">
                <div className="absolute inset-0 flex flex-col justify-evenly px-2">
                  <div className="h-0.5 bg-cyan-400/60"></div>
                  <div className="h-0.5 bg-cyan-400/40"></div>
                  <div className="h-0.5 bg-cyan-400/80"></div>
                  <div className="h-0.5 bg-cyan-400/30"></div>
                </div>
              </div>
              <h3 className="text-xl font-bold text-white mb-3">Project Levels</h3>
              <p className="text-slate-400">Fibonacci ratios mark decision coordinates</p>
            </div>

            {/* Arrow */}
            <div className="hidden md:flex items-center justify-center md:col-start-2 md:col-end-3 md:row-start-1">
              <svg className="w-8 h-8 text-slate-600 rotate-90 md:rotate-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>

            {/* Step 3 */}
            <div className="glass p-8 rounded-xl text-center md:col-start-3">
              <div className="w-16 h-16 mx-auto mb-6 bg-slate-800 rounded-xl flex items-center justify-center">
                <svg className="w-10 h-10 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
              <h3 className="text-xl font-bold text-white mb-3">Watch Price</h3>
              <p className="text-slate-400">Levels identified before price arrives</p>
            </div>
          </div>
        </div>
      </section>

      {/* The 2022 Proof Section */}
      <section className="py-20 px-6 bg-slate-900">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-white text-center mb-12">ES Futures, Bear Market</h2>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-12">
            {[
              { value: '20,000', label: 'bars' },
              { value: '37', label: 'XL swings' },
              { value: '4336', label: '0.618 level' },
              { value: String.fromCharCode(10003), label: 'respected' },
            ].map((stat) => (
              <div key={stat.label} className="text-center">
                <p className="text-4xl md:text-5xl font-mono font-bold text-white mb-2">{stat.value}</p>
                <p className="text-xs text-slate-500 uppercase tracking-widest">{stat.label}</p>
              </div>
            ))}
          </div>

          <div className="max-w-3xl mx-auto text-center mb-12">
            <p className="text-lg text-slate-300 leading-relaxed mb-8">
              The system processed the 2022 ES futures data. Found 37 XL-scale reference swings. Projected the 0.618 retracement at 4336.
            </p>
            <p className="text-lg text-white font-medium">
              Price rallied, hit 4336, reversed.
            </p>
            <p className="text-slate-400 mt-4">
              The system knew that level mattered—before price got there.
            </p>
          </div>

          <div className="glass p-8 rounded-2xl border-cyan-500/30 max-w-3xl mx-auto">
            <div className="flex items-start gap-4">
              <div className="text-4xl text-cyan-400">"</div>
              <p className="text-lg md:text-xl text-white italic leading-relaxed">
                That's not backtesting. That's not lookahead. The algo found the skeleton, found the levels, and price respected them.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Fibonacci Levels Section */}
      <section className="py-20 px-6">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-white text-center mb-4">Decision Coordinates</h2>
          <p className="text-slate-400 text-center mb-12">The Fibonacci levels that define market structure</p>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            {fibLevels.map((fib) => (
              <div key={fib.level} className="glass p-6 rounded-xl hover:border-cyan-500/50 transition-all text-center">
                <p className={`text-3xl font-mono font-bold mb-2 ${fib.color}`}>{fib.level}</p>
                <h3 className="text-sm font-bold text-white mb-2">{fib.name}</h3>
                <p className="text-xs text-slate-400">{fib.copy}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Multi-Timeframe Section */}
      <section className="py-20 px-6 bg-slate-950/50">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-white text-center mb-4">Structure Nests Inside Structure</h2>
          <p className="text-slate-400 text-center mb-12 max-w-2xl mx-auto">
            Trade with the larger structure, not against it. Minute swings nest inside hourly swings, which nest inside daily, weekly, monthly.
          </p>

          {/* Nested Timeframe Visual */}
          <div className="max-w-2xl mx-auto">
            <div className="glass p-8 rounded-xl border-slate-600">
              <div className="text-xs text-slate-500 uppercase tracking-widest mb-4">MONTHLY</div>
              <div className="glass p-6 rounded-lg border-slate-600 ml-4">
                <div className="text-xs text-slate-500 uppercase tracking-widest mb-4">WEEKLY</div>
                <div className="glass p-5 rounded-lg border-slate-600 ml-4">
                  <div className="text-xs text-slate-500 uppercase tracking-widest mb-4">DAILY</div>
                  <div className="glass p-4 rounded-lg border-cyan-500/50 ml-4">
                    <div className="text-xs text-cyan-400 uppercase tracking-widest">HOURLY</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-8">See Your Markets</h2>

          <button
            onClick={handleLogin}
            className="px-8 py-4 bg-white text-slate-900 font-bold rounded-xl hover:bg-cyan-500 hover:text-white transition-all transform hover:scale-105 active:scale-95 shadow-2xl shadow-cyan-500/20"
          >
            Try the Demo
          </button>
        </div>
      </section>

      <Footer />
    </div>
  );
};
