import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { Menu, Search, X } from 'lucide-react';
import LogoMark from './LogoMark';
import './Header.css';

const NAV_ITEMS = [
  { label: 'Dashboard', to: '/', id: 'nav-dashboard', end: true },
  { label: 'Documents', to: '/documents', id: 'nav-documents' },
  { label: 'Claims', to: '/claims', id: 'nav-claims' },
  { label: 'AI search', to: '/rag-search', id: 'nav-ai-search' },
  { label: 'Validation', to: '/validation', id: 'nav-validation' },
];

/** Top bar: product mark, the five sections, and a claims search (a menu on small screens). */
export default function Header() {
  const location = useLocation();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPath, setMenuPath] = useState(location.pathname);
  const menuButtonRef = useRef(null);

  // Close the menu whenever the route changes (adjusting state during render,
  // so the closed menu is never painted on the new page).
  if (menuPath !== location.pathname) {
    setMenuPath(location.pathname);
    setMenuOpen(false);
  }

  useEffect(() => {
    if (!menuOpen) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [menuOpen]);

  // The claims list has its own search field, so the header's is hidden there
  // (it stays mounted so its cleared state carries over to the next page).
  const onClaimsList = location.pathname === '/claims';

  // Searches run on the Claims page, which queries GET /claims?search=...
  const handleSearch = (event) => {
    event.preventDefault();
    const term = query.trim();
    navigate(term ? `/claims?${new URLSearchParams({ search: term })}` : '/claims');
    setQuery('');
  };

  return (
    <header className="topbar" role="banner">
      <div className="topbar-inner">
        <Link to="/" className="topbar-brand" aria-label="IntelliClaim AI, dashboard">
          <LogoMark />
          <span className="topbar-brand-name" translate="no">IntelliClaim AI</span>
        </Link>

        <button
          ref={menuButtonRef}
          type="button"
          className="topbar-menu-button"
          aria-expanded={menuOpen}
          aria-controls="topbar-menu"
          onClick={() => setMenuOpen((open) => !open)}
          id="topbar-menu-button"
        >
          {menuOpen ? <X size={18} aria-hidden="true" /> : <Menu size={18} aria-hidden="true" />}
          Menu
        </button>

        <div id="topbar-menu" className="topbar-menu" data-open={menuOpen}>
          <nav className="topbar-nav" aria-label="Main">
            <ul role="list">
              {NAV_ITEMS.map((item) => (
                <li key={item.to}>
                  <NavLink to={item.to} end={item.end} id={item.id} className="topbar-link">
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>

          <form className={`topbar-search ${onClaimsList ? 'topbar-search--hidden' : ''}`} role="search" onSubmit={handleSearch}>
            <Search size={16} className="topbar-search-icon" aria-hidden="true" />
            <input
              id="header-search-input"
              className="topbar-search-input"
              type="search"
              name="search"
              autoComplete="off"
              spellCheck={false}
              placeholder="Claim, policy, patient or diagnosis…"
              aria-label="Search claims"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </form>
        </div>
      </div>
    </header>
  );
}
