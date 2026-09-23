import Markdown from 'react-markdown';
import { Link, Navigate, useParams } from 'react-router-dom';
import { DOCS, findDoc } from './registry';

/** Renders one registered document plus a pill nav to the other sections. */
export function DocPage() {
  const { docId } = useParams();
  const doc = findDoc(docId);

  if (!doc) return <Navigate to="/docs" replace />;

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <p className="text-sm">
        <Link to="/docs" className="text-brand-400 hover:text-brand-300">
          ← All docs
        </Link>
      </p>

      {/* Section nav — mirrors DocsIndex order */}
      <nav className="flex flex-wrap gap-2 not-prose">
        {DOCS.map((d) => (
          <Link
            key={d.id}
            to={`/docs/${d.id}`}
            className={
              d.id === doc.id
                ? 'rounded-full bg-brand-500/20 border border-brand-600 px-3 py-1 text-sm text-brand-200'
                : 'rounded-full border border-slate-700 px-3 py-1 text-sm text-slate-400 hover:border-slate-500 hover:text-slate-200'
            }
          >
            {d.title}
          </Link>
        ))}
      </nav>

      <article className="prose prose-invert prose-headings:text-white prose-a:text-brand-400">
        <Markdown>{doc.md}</Markdown>
      </article>
    </div>
  );
}
