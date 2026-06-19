import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  FileText,
  ClipboardList,
  Search,
  ShieldCheck,
  Settings,
  BrainCircuit,
  Menu,
  X,
} from 'lucide-react';
import './Sidebar.css';

const navItems = [
  { label: 'Dashboard', path: '/', icon: LayoutDashboard },
  { label: 'Documents', path: '/documents', icon: FileText },
  { label: 'Claims', path: '/claims', icon: ClipboardList },
  { label: 'RAG Search', path: '/rag-search', icon: Search },
  { label: 'Validation', path: '/validation', icon: ShieldCheck, badge: 3 },
];

export default function Sidebar({ isOpen, onToggle }) {
  const location = useLocation();

  return (
    <>
      {isOpen && (
        <div className="sidebar-backdrop" onClick={onToggle} />
      )}

      <button
        id="sidebar-toggle-btn"
        className="sidebar-toggle"
        onClick={onToggle}
        aria-label="Toggle sidebar"
      >
        {isOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      <nav
        className={`sidebar ${isOpen ? 'open' : ''}`}
        role="navigation"
        aria-label="Main navigation"
      >
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">
            <BrainCircuit size={22} color="white" />
          </div>
          <span className="sidebar-logo-text">IntelliClaim</span>
        </div>

        <div className="sidebar-nav">
          <span className="sidebar-section-label">Menu</span>
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive =
              item.path === '/'
                ? location.pathname === '/'
                : location.pathname.startsWith(item.path);

            return (
              <NavLink
                key={item.path}
                to={item.path}
                id={`nav-${item.label.toLowerCase().replace(/\s/g, '-')}`}
                className={`sidebar-link ${isActive ? 'active' : ''}`}
                onClick={() => {
                  if (window.innerWidth <= 768) onToggle?.();
                }}
              >
                <span className="sidebar-link-icon">
                  <Icon size={18} />
                </span>
                <span>{item.label}</span>
                {item.badge && (
                  <span className="sidebar-link-badge">{item.badge}</span>
                )}
              </NavLink>
            );
          })}
        </div>

        <div className="sidebar-bottom">
          <div className="sidebar-bottom-row">
            <span className="sidebar-version">v1.0.0</span>
            <button
              id="sidebar-settings-btn"
              className="sidebar-settings-btn"
              aria-label="Settings"
            >
              <Settings size={16} />
            </button>
          </div>
        </div>
      </nav>
    </>
  );
}
