import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { copyFileSync } from 'node:fs';
import { resolve } from 'node:path';

// Copy showcase assets from the sibling `docs/showcase/` directory into the
// build output so they ship with the site on GitHub Pages.
import { viteStaticCopy } from 'vite-plugin-static-copy';

const showcaseDir = resolve(__dirname, '..', 'docs', 'showcase');

/**
 * GitHub Pages serves `404.html` for unknown paths (e.g. a direct hit on
 * `/docs`). Copying index.html there lets react-router take over the route
 * instead of showing a dead 404 page. The response still carries a 404
 * status — harmless for this site, but keep it in mind for SEO tooling.
 */
function spaFallback(): Plugin {
  return {
    name: 'spa-404-fallback',
    apply: 'build',
    closeBundle() {
      const out = resolve(__dirname, 'dist');
      copyFileSync(resolve(out, 'index.html'), resolve(out, '404.html'));
    },
  };
}

export default defineConfig({
  plugins: [
    react(),
    viteStaticCopy({
      // Glob (`showcase/*`), not the bare dir: copying the dir itself would
      // nest the assets under dist/showcase/showcase/.
      targets: [{ src: `${showcaseDir}/*`, dest: 'showcase' }],
    }),
    spaFallback(),
  ],
  // Custom domain (sprout-toolkit.tzinny.com) serves the site from the
  // domain root. The legacy https://tzinny-dev.github.io/sprout-toolkit URL
  // is redirected to the custom domain by the inline script in index.html
  // (GitHub's own default-domain redirect may preserve the project prefix).
  // NOTE: publishing this change requires the custom domain's DNS to be
  // active — with base '/', assets on github.io would 404 otherwise.
  base: '/',
  build: {
    // Must NOT be `../dist`: that directory belongs to the Python package
    // builds (python -m build / twine upload) and CI wipes it on release.
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          // Keep vendor split small on a landing page
          react: ['react', 'react-dom'],
        },
      },
    },
  },
});
