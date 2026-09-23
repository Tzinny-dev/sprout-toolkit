import type { ReactNode } from 'react';
import { Link, Outlet, NavLink } from 'react-router-dom';
import { Logo } from '../components/Logo';

const nav = [
  { to: '/', label: 'Home' },
  { to: '/docs', label: 'Docs' },
];

export function Layout() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-brand-950 via-brand-900 to-brand-950 text-slate-100">
      <header className="container mx-auto px-4 py-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3">
          <Logo className="h-8 w-8 text-brand-400" />
          <span className="font-semibold text-xl text-white">sprout-toolkit</span>
        </Link>
        <nav className="flex items-center gap-6 text-sm">
          {nav.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              end
              className={({ isActive }) =>
                isActive
                  ? 'text-brand-300'
                  : 'text-slate-400 hover:text-slate-200'
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="container mx-auto px-4 py-12">
        <Outlet />
      </main>
      <footer className="border-t border-slate-800 mt-16">
        <div className="container mx-auto px-4 py-6 text-sm text-slate-500">
          <span className="font-mono">pip install sprout-toolkit</span> · MIT licensed ·{' '}
          <a
            href="https://github.com/Tzinny-dev/sprout-toolkit"
            className="underline hover:text-slate-300"
            target="_blank"
            rel="noreferrer"
          >
            GitHub
          </a>
        </div>
      </footer>
    </div>
  );
}
