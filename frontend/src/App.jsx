import { lazy, Suspense } from 'react';
import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout/Layout';
import { LoadingState } from './components/Shared/StateMessage';

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
    <Suspense fallback={<LoadingState label="Loading page…" />}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/claims" element={<ClaimsPage />} />
          <Route path="/claims/:id" element={<ClaimDetailPage />} />
          <Route path="/rag-search" element={<RAGSearchPage />} />
          <Route path="/validation" element={<ValidationPage />} />
          <Route path="*" element={
            <div className="page-enter" style={{ textAlign: 'center', paddingTop: 120 }}>
              <h1 style={{ fontSize: '4rem', background: 'var(--accent-gradient)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>404</h1>
              <p style={{ color: 'var(--text-secondary)', marginTop: 8 }}>Page not found</p>
            </div>
          } />
        </Route>
      </Routes>
    </Suspense>
  );
}
