import { Link, useNavigate } from 'react-router-dom';
import { ClipboardList, Search, X } from 'lucide-react';
import { getErrorMessage } from '../../services/api';
import { formatCurrency, formatDate } from '../../utils/format';
import { StatusBadge } from '../Shared/Badge';
import RiskValue from '../Shared/RiskValue';
import { EmptyState, ErrorState, LoadingState } from '../Shared/StateMessage';
import './ClaimsList.css';

const STATUSES = ['all', 'pending', 'approved', 'rejected', 'flagged'];

function ClaimsTable({ claims }) {
  const navigate = useNavigate();

  // Clicking anywhere on a row opens the claim; the claim number is the real
  // link, so keyboard, middle-click and Cmd/Ctrl-click work as usual.
  const openRow = (event, id) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (event.target.closest('a, button')) return;
    if (window.getSelection()?.toString()) return;
    navigate(`/claims/${id}`);
  };

  return (
    <table className="claims-table" role="table">
      <thead role="rowgroup">
        <tr role="row">
          <th scope="col" role="columnheader">Claim</th>
          <th scope="col" role="columnheader" className="claims-col-policy">Policy</th>
          <th scope="col" role="columnheader">Patient</th>
          <th scope="col" role="columnheader">Diagnosis</th>
          <th scope="col" role="columnheader" className="claims-col-number">Amount</th>
          <th scope="col" role="columnheader">Risk</th>
          <th scope="col" role="columnheader">Status</th>
          <th scope="col" role="columnheader" className="claims-col-number">Received</th>
        </tr>
      </thead>
      <tbody role="rowgroup">
        {claims.map((claim) => (
          <tr key={claim.id} role="row" className="claims-row" onClick={(event) => openRow(event, claim.id)}>
            <td role="cell" className="claims-cell-claim" translate="no">
              <Link to={`/claims/${claim.id}`} className="record-link">
                {claim.claim_number || 'Unnumbered claim'}
              </Link>
            </td>
            <td role="cell" className="claims-col-policy claims-cell-muted tabular" translate="no">{claim.policy_number || '—'}</td>
            <td role="cell" className="claims-cell-patient">{claim.patient_name || '—'}</td>
            <td role="cell" className="claims-cell-diagnosis" title={claim.diagnosis || undefined}>{claim.diagnosis || '—'}</td>
            <td role="cell" className="claims-col-number claims-cell-amount tabular">{formatCurrency(claim.treatment_cost)}</td>
            <td role="cell" className="claims-cell-risk"><RiskValue score={claim.risk_score} /></td>
            <td role="cell" className="claims-cell-status"><StatusBadge status={claim.status} /></td>
            <td role="cell" className="claims-col-number claims-cell-date claims-cell-muted tabular">
              {formatDate(claim.created_at, { month: 'short', day: 'numeric' })}
            </td>
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
  onClearFilters,
}) {
  const filtered = search.trim() !== '' || status !== 'all';

  let content;
  if (error) {
    content = <ErrorState title="Couldn't load claims" message={getErrorMessage(error)} onRetry={onRetry} />;
  } else if (!claims) {
    content = <LoadingState label="Loading claims…" />;
  } else if (claims.length === 0 && filtered) {
    content = (
      <EmptyState
        icon={Search}
        title="No claims match your filters"
        action={(
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onClearFilters}
          >
            <X size={14} aria-hidden="true" /> Clear search and filters
          </button>
        )}
      >
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
      <div className="claims-toolbar">
        <div className="claims-search">
          <Search size={16} className="claims-search-icon" aria-hidden="true" />
          <input
            type="search"
            name="search"
            autoComplete="off"
            spellCheck={false}
            placeholder="Claim, policy, patient or diagnosis…"
            aria-label="Search claims"
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            className="claims-search-input"
            id="claims-search-input"
          />
        </div>
        <div className="claims-filter" role="group" aria-label="Filter by status">
          {STATUSES.map((value) => (
            <button
              key={value}
              type="button"
              className="claims-filter-option"
              aria-pressed={status === value}
              onClick={() => onStatusChange(value)}
              id={`filter-${value}`}
            >
              {value.charAt(0).toUpperCase() + value.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className={`claims-table-wrapper ${loading && claims ? 'claims-table-wrapper--refreshing' : ''}`} aria-busy={loading}>
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
