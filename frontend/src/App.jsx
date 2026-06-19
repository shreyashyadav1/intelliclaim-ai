import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout/Layout';
import DashboardPage from './pages/DashboardPage';
import DocumentsPage from './pages/DocumentsPage';
import ClaimsPage from './pages/ClaimsPage';
import ClaimDetailPage from './pages/ClaimDetailPage';
import RAGSearchPage from './pages/RAGSearchPage';
import ValidationPage from './pages/ValidationPage';

export default function App() {
  return (
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
  );
}
