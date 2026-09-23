import React from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Home } from './pages/Home';
import { DocsIndex } from './pages/docs/DocsIndex';
import { DocPage } from './pages/docs/DocPage';
import './index.css';

const router = createBrowserRouter(
  [
    {
      path: '/',
      element: <Layout />,
      children: [
        { index: true, element: <Home /> },
        {
          path: 'docs',
          children: [
            { index: true, element: <DocsIndex /> },
            { path: ':docId', element: <DocPage /> },
          ],
        },
      ],
    },
  ],
  // BASE_URL is '/sprout-toolkit/' under the legacy project-site base and
  // '/' on the custom domain. react-router wants '/' (its default) rather
  // than the empty string that a naive trailing-slash strip would produce.
  { basename: import.meta.env.BASE_URL.replace(/\/$/, '') || '/' },
);

createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
