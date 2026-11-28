import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import './Shared.css';

const APP_NAME = 'IntelliClaim AI';

/**
 * The heading block every page starts with. `title` also names the browser tab;
 * set `identifier` when the title is an ID (e.g. a claim number) so browsers
 * don't machine-translate it. `back` ({ to, label }) links to the parent page,
 * `meta` sits beside the title (e.g. a status tag) and `actions` holds the
 * page's buttons.
 */
export default function PageHeader({ title, description, identifier = false, back, meta, actions }) {
  useEffect(() => {
    document.title = title ? `${title} | ${APP_NAME}` : APP_NAME;
  }, [title]);

  return (
    <div className="page-header">
      <div className="page-header-text">
        {back && (
          <Link to={back.to} className="page-header-back">
            <ArrowLeft size={16} aria-hidden="true" /> {back.label}
          </Link>
        )}
        <div className="page-header-title-row">
          <h1 translate={identifier ? 'no' : undefined}>{title}</h1>
          {meta}
        </div>
        {description && <p className="page-header-description">{description}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </div>
  );
}
