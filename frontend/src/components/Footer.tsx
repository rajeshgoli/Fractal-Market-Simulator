import { Link } from 'react-router-dom';

interface FooterProps {
  className?: string;
}

export const Footer: React.FC<FooterProps> = ({ className = '' }) => {
  const columns = [
    {
      title: 'Product',
      links: [
        { label: 'Features', href: '/#features' },
        { label: 'Pricing', href: '#' },
        { label: 'Demo', href: '/login' },
      ],
    },
    {
      title: 'Developers',
      links: [
        { label: "How It's Built", href: '/developers' },
        { label: 'GitHub', href: 'https://github.com/rajeshgoli/Fractal-Market-Simulator', external: true },
        { label: 'Docs', href: '#' },
      ],
    },
    {
      title: 'Company',
      links: [
        { label: 'Story', href: '/story' },
        { label: 'Contact', href: '#' },
      ],
    },
    {
      title: 'Legal',
      links: [
        { label: 'Privacy', href: '#' },
        { label: 'Terms', href: '#' },
      ],
    },
  ];

  return (
    <footer className={`py-16 px-6 border-t border-white/5 bg-slate-950 ${className}`}>
      <div className="max-w-7xl mx-auto">
        {/* Links grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-12">
          {columns.map((column) => (
            <div key={column.title}>
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4">
                {column.title}
              </h3>
              <ul className="space-y-3">
                {column.links.map((link) => (
                  <li key={link.label}>
                    {link.external ? (
                      <a
                        href={link.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-slate-500 hover:text-white transition-colors"
                      >
                        {link.label}
                      </a>
                    ) : link.href.startsWith('/') ? (
                      <Link
                        to={link.href}
                        className="text-sm text-slate-500 hover:text-white transition-colors"
                      >
                        {link.label}
                      </Link>
                    ) : (
                      <a
                        href={link.href}
                        className="text-sm text-slate-500 hover:text-white transition-colors"
                      >
                        {link.label}
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div className="pt-8 border-t border-white/5 flex flex-col md:flex-row justify-between items-center gap-4">
          <div className="flex items-center space-x-4">
            <div className="w-6 h-6 bg-cyan-500 rounded flex items-center justify-center font-bold text-slate-900 text-xs">
              F
            </div>
            <span className="font-bold text-slate-300">FRACTAL MARKET</span>
          </div>

          <div className="flex items-center space-x-6">
            <a
              href="https://x.com/rajeshgoli"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-slate-500 hover:text-white transition-colors"
            >
              Twitter
            </a>
            <a
              href="https://github.com/rajeshgoli/Fractal-Market-Simulator"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-slate-500 hover:text-white transition-colors"
            >
              GitHub
            </a>
          </div>
        </div>

        {/* Copyright */}
        <div className="mt-8 text-center text-[10px] text-slate-700 uppercase tracking-widest font-bold">
          &copy; 2026 Fractal Market. All rights reserved.
        </div>
      </div>
    </footer>
  );
};
