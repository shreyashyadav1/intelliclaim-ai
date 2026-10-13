import { Link, useNavigate } from 'react-router-dom';
import { ClipboardList, Search } from 'lucide-react';
import { getErrorMessage } from '../../services/api';
import { formatCurrency, formatDate, formatScore, riskColor } from '../../utils/format';
import Badge from '../Shared/Badge';
import { EmptyState, ErrorState, LoadingState } from '../Shared/StateMessage';
import './ClaimsList.css';

const STATUSES = ['all', 'pending', 'approved', 'rejected', 'flagged'];

function ClaimsTable({ claims }) {
  const navigate = useNavigate();

  return (
    <table className="claims-table">
      <thead>
        <tr>
          <th>Claim #</th>
          <th>Policy #</th>
          <th>Patient</th>
          <th>Diagnosis</th>
          <th>Cost</th>
          <th>Status</th>
          <th>Risk</th>
          <th>Date</th>
        </tr>
      </thead>
      <tbody>
        {claims.map((claim) => (
          <tr key={claim.id} className="claims-table-row" onClick={() => navigate(`/claims/${claim.id}`)}>
            <td className="mono-cell accent">
              <Link to={`/claims/${claim.id}`} onClick={(event) => event.stopPropagation()}>
                {claim.claim_number || 'Unnumbered claim'}
              </Link>
            </td>
            <td className="mono-cell">{claim.policy_number || '—'}</td>
            <td>{claim.patient_name || '—'}</td>
            <td className="diagnosis-cell">{claim.diagnosis || '—'}</td>
            <td className="mono-cell bold">{formatCurrency(claim.treatment_cost)}</td>
            <td><Badge variant={claim.status}>{claim.status}</Badge></td>
            <td>
              <span
                className="risk-pill"
                style={{ color: riskColor(claim.risk_score), background: `${riskColor(claim.risk_score)}15` }}
              >
                {formatScore(claim.risk_score)}
              </span>
            </td>
            <td className="date-cell">{formatDate(claim.created_at, { month: 'short', day: 'numeric' })}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function ClaimsList({
  claims,
  total,
  loading,
  error,
  onRetry,
  search,
  onSearchChange,
  status,
  onStatusChange,
}) {
  const filtered = search.trim() !== '' || status !== 'all';

  let content;
  if (error) {
    content = <ErrorState title="Couldn't load claims" message={getErrorMessage(error)} onRetry={onRetry} />;
  } else if (!claims) {
    content = <LoadingState label="Loading claims…" />;
  } else if (claims.length === 0 && filtered) {
    content = (
      <EmptyState icon={Search} title="No claims match your filters">
        Try a different search term or status.
      </EmptyState>
    );
  } else if (claims.length === 0) {
    content = (
      <EmptyState icon={ClipboardList} title="No claims yet">
        <Link to="/documents">Upload a document</Link> and extract it to create the first claim.
      </EmptyState>
    );
  } else {
    content = <ClaimsTable claims={claims} />;
  }

  return (
    <div className="claims-list" id="claims-list">
      <div className="claims-list-toolbar">
        <div className="claims-search-wrapper">
          <Search size={16} className="claims-search-icon" aria-hidden="true" />
          <input
            type="search"
            placeholder="Search claims..."
            aria-label="Search claims"
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            className="claims-search-input"
            id="claims-search-input"
          />
        </div>
        <div className="claims-filter-tabs" role="group" aria-label="Filter by status">
          {STATUSES.map((value) => (
            <button
              key={value}
              type="button"
              className={`claims-filter-tab ${status === value ? 'active' : ''}`}
              aria-pressed={status === value}
              onClick={() => onStatusChange(value)}
              id={`filter-${value}`}
            >
              {value.charAt(0).toUpperCase() + value.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div
        className={`claims-table-wrapper glass-card ${loading && claims ? 'claims-table-wrapper--refreshing' : ''}`}
        aria-busy={loading}
      >
        {content}
      </div>

      {claims && total > claims.length && (
        <p className="claims-list-footnote">
          Showing the {claims.length} most recent of {total} claims. Refine the search to narrow the list.
        </p>
      )}
    </div>
  );
}
