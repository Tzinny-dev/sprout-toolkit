// Registry of every document under /docs. Both DocsIndex (cards) and
// DocPage (render + section nav) read from this single source.
// Markdown is inlined at build time via Vite's `?raw` imports.
import quickstart from '../../../../docs/starter-tutorial.md?raw';
import cli from '../../../../docs/cli.md?raw';
import generators from '../../../../docs/generators.md?raw';
import spec from '../../../../docs/spec.md?raw';
import api from '../../../../docs/api.md?raw';

export interface DocEntry {
  id: string;
  title: string;
  description: string;
  md: string;
}

export const DOCS: DocEntry[] = [
  {
    id: 'quickstart',
    title: 'Quickstart',
    description:
      'From pip install to sprites on screen in a fresh Expo app — 10 minutes, no git clone.',
    md: quickstart,
  },
  {
    id: 'spec',
    title: 'Spec schema',
    description:
      'Every field of a spec JSON: name, seed, layout, items, animations, runtime shader.',
    md: spec,
  },
  {
    id: 'generators',
    title: 'Generators',
    description:
      'The 6 generators and their params with defaults: terrain, blob_walk, props, particles, ui, font.',
    md: generators,
  },
  {
    id: 'cli',
    title: 'CLI reference',
    description:
      'All commands (init, generate, batch, watch, info, lint, diff, validate) and export options.',
    md: cli,
  },
  {
    id: 'api',
    title: 'Manifest & index.ts API',
    description:
      'manifest.json contract and the typed exports of the generated index.ts (Atlas hooks, lookup helpers).',
    md: api,
  },
];

export function findDoc(id: string | undefined): DocEntry | undefined {
  return DOCS.find((d) => d.id === id);
}
