import { useLocation } from 'react-router-dom';
import { Search, Bell } from 'lucide-react';
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
  const basePath = '/' + (location.pathname.split('/')[1] || '');
  const page = pageTitles[basePath] || pageTitles['/'];

  return (
    <header className="header" role="banner">
      <div className="header-left">
        <h1 className="header-title">{page.title}</h1>
        <p className="header-subtitle">{page.subtitle}</p>
      </div>

      <div className="header-right">
        <div className="header-search">
          <Search size={16} className="header-search-icon" />
          <input
            id="header-search-input"
            className="header-search-input"
            type="search"
            placeholder="Search claims, documents..."
            aria-label="Search"
          />
        </div>

        <button
          id="header-notifications-btn"
          className="header-icon-btn"
          aria-label="Notifications"
        >
          <Bell size={18} />
          <span className="header-notification-badge" />
        </button>

        <div
          id="header-avatar"
          className="header-avatar"
          role="button"
          tabIndex={0}
          aria-label="User profile"
        >
          SY
        </div>
      </div>
    </header>
  );
}
