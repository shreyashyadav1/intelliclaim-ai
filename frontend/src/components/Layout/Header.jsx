import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Search } from 'lucide-react';
import './Header.css';

const pageTitles = {
  '/': { title: 'Dashboard', subtitle: 'Overview of claims activity and key metrics' },
  '/documents': { title: 'Documents', subtitle: 'Upload and manage insurance documents' },
  '/claims': { title: 'Claims', subtitle: 'Review and process insurance claims' },
  '/rag-search': { title: 'AI Search', subtitle: 'Query your documents with AI-powered search' },
  '/validation': { title: 'Validation', subtitle: 'Review flagged claims and risk assessments' },
};

export default function Header() {
  const location = useLocation();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const basePath = '/' + (location.pathname.split('/')[1] || '');
  const page = pageTitles[basePath] || pageTitles['/'];

  // Searches run on the Claims page, which queries GET /claims?search=...
  const handleSearch = (event) => {
    event.preventDefault();
    const term = query.trim();
    navigate(term ? `/claims?${new URLSearchParams({ search: term })}` : '/claims');
    setQuery('');
  };

  return (
    <header className="header" role="banner">
      <div className="header-left">
        <h1 className="header-title">{page.title}</h1>
        <p className="header-subtitle">{page.subtitle}</p>
      </div>

      <div className="header-right">
        <form className="header-search" role="search" onSubmit={handleSearch}>
          <Search size={16} className="header-search-icon" aria-hidden="true" />
          <input
            id="header-search-input"
            className="header-search-input"
            type="search"
            placeholder="Search claims..."
            aria-label="Search claims"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </form>
      </div>
    </header>
  );
}
