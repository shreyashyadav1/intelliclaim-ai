import { Link, useNavigate } from 'react-router-dom';
import { ClipboardList, ExternalLink } from 'lucide-react';
import { getErrorMessage } from '../../services/api';
import { formatCurrency, formatScore, riskColor } from '../../utils/format';
import Badge from '../Shared/Badge';
import { EmptyState, ErrorState, LoadingState } from '../Shared/StateMessage';
import './RecentClaims.css';

function ClaimsTable({ claims }) {
  const navigate = useNavigate();

  return (
    <div className="recent-claims-table-wrapper">
      <table className="recent-claims-table">
        <thead>
          <tr>
            <th>Claim #</th>
            <th>Patient</th>
            <th>Diagnosis</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Risk</th>
          </tr>
        </thead>
        <tbody>
          {claims.map((claim) => (
            <tr key={claim.id} onClick={() => navigate(`/claims/${claim.id}`)} className="recent-claims-row">
              <td className="claim-number-cell">
                <Link to={`/claims/${claim.id}`} onClick={(event) => event.stopPropagation()}>
                  {claim.claim_number || 'Unnumbered claim'}
                </Link>
              </td>
              <td>{claim.patient_name || '—'}</td>
              <td className="diagnosis-cell">{claim.diagnosis || '—'}</td>
              <td className="amount-cell">{formatCurrency(claim.treatment_cost)}</td>
              <td><Badge variant={claim.status}>{claim.status}</Badge></td>
              <td>
                <span
                  className="risk-score-badge"
                  style={{ color: riskColor(claim.risk_score), background: `${riskColor(claim.risk_score)}15` }}
                >
                  {formatScore(claim.risk_score)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function RecentClaims({ data, error, onRetry }) {
  const navigate = useNavigate();

  let body;
  if (error) {
    body = <ErrorState title="Couldn't load recent claims" message={getErrorMessage(error)} onRetry={onRetry} />;
  } else if (!data) {
    body = <LoadingState label="Loading recent claims…" />;
  } else if (data.length === 0) {
    body = (
      <EmptyState icon={ClipboardList} title="No claims yet">
        <Link to="/documents">Upload a document</Link> and extract it to create the first claim.
      </EmptyState>
    );
  } else {
    body = <ClaimsTable claims={data} />;
  }

  return (
    <div className="recent-claims glass-card" id="recent-claims-table">
      <div className="recent-claims-header">
        <h3 className="recent-claims-title">Recent Claims</h3>
        <button className="recent-claims-view-all" onClick={() => navigate('/claims')} id="view-all-claims-btn">
          View All <ExternalLink size={14} />
        </button>
      </div>
      {body}
    </div>
  );
}
