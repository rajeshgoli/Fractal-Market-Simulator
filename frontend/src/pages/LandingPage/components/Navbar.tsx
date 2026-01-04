import { Link } from 'react-router-dom';

interface NavbarProps {
  onLogin: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ onLogin }) => {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 glass border-b border-white/10 px-6 py-4">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <Link to="/" className="flex items-center space-x-2">
          <div className="w-8 h-8 bg-cyan-500 rounded flex items-center justify-center font-bold text-slate-900">F</div>
          <span className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
            FRACTAL MARKET
          </span>
        </Link>

        <div className="hidden md:flex items-center space-x-8 text-sm font-medium text-slate-400">
          <Link to="/developers" className="hover:text-white transition-colors">Developers</Link>
          <Link to="/traders" className="hover:text-white transition-colors">Traders</Link>
          <Link to="/story" className="hover:text-white transition-colors">Story</Link>
          <a href="https://github.com/rajeshgoli/Fractal-Market-Simulator" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">GitHub</a>
        </div>

        <div className="flex items-center space-x-4">
          <button
            onClick={onLogin}
            className="text-sm font-medium text-slate-300 hover:text-white transition-colors"
          >
            Log in
          </button>
          <button
            onClick={onLogin}
            className="bg-cyan-600 hover:bg-cyan-500 text-white px-4 py-2 rounded-lg text-sm font-bold transition-all transform hover:scale-105 active:scale-95 shadow-lg shadow-cyan-900/20"
          >
            Get Started
          </button>
        </div>
      </div>
    </nav>
  );
};
