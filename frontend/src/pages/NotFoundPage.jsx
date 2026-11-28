import { Link } from 'react-router-dom';
import PageHeader from '../components/Shared/PageHeader';

export default function NotFoundPage() {
  return (
    <div id="not-found-page">
      <PageHeader
        title="Page not found"
        description="This address doesn’t match a page in IntelliClaim. Check the link, or start again from the dashboard."
      />
      <div className="page-header-actions">
        <Link to="/" className="btn btn-primary">Go to the dashboard</Link>
        <Link to="/claims" className="btn btn-secondary">Open the claims list</Link>
      </div>
    </div>
  );
}
