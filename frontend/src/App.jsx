import { lazy, Suspense } from 'react';
import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout/Layout';
import { LoadingState } from './components/Shared/StateMessage';
import NotFoundPage from './pages/NotFoundPage';

// Route-level code splitting keeps the initial bundle small; each page (and
// its own heavy dependencies, e.g. recharts or react-dropzone) loads on demand.
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const DocumentsPage = lazy(() => import('./pages/DocumentsPage'));
const ClaimsPage = lazy(() => import('./pages/ClaimsPage'));
const ClaimDetailPage = lazy(() => import('./pages/ClaimDetailPage'));
const RAGSearchPage = lazy(() => import('./pages/RAGSearchPage'));
const ValidationPage = lazy(() => import('./pages/ValidationPage'));

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Page><DashboardPage /></Page>} />
        <Route path="/documents" element={<Page><DocumentsPage /></Page>} />
        <Route path="/claims" element={<Page><ClaimsPage /></Page>} />
        <Route path="/claims/:id" element={<Page><ClaimDetailPage /></Page>} />
        <Route path="/rag-search" element={<Page><RAGSearchPage /></Page>} />
        <Route path="/validation" element={<Page><ValidationPage /></Page>} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

/** Lazy pages suspend inside the layout, so the top bar stays put while a page loads. */
function Page({ children }) {
  return <Suspense fallback={<LoadingState label="Loading page…" />}>{children}</Suspense>;
}
