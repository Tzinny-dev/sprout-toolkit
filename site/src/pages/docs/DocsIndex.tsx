import { Link } from 'react-router-dom';
import { DOCS } from './registry';

export function DocsIndex() {
  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <header className="text-center space-y-3">
        <h1 className="text-3xl font-bold text-white">Documentation</h1>
        <p className="text-slate-400">
          Everything from your first <code className="text-brand-300">pip install</code> to
          the manifest/index.ts contract your app consumes.
        </p>
      </header>
      <div className="grid gap-4 sm:grid-cols-2">
        {DOCS.map((d) => (
          <Link
            key={d.id}
            to={`/docs/${d.id}`}
            className="group rounded-lg border border-slate-800 bg-slate-900/50 p-5 transition hover:border-brand-700 hover:bg-slate-900"
          >
            <h2 className="font-medium text-brand-300 group-hover:text-brand-200">
              {d.title} →
            </h2>
            <p className="mt-2 text-sm text-slate-400">{d.description}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
