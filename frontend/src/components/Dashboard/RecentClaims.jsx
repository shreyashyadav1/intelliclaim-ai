import { Link } from 'react-router-dom';
import { ClipboardList } from 'lucide-react';
import { getErrorMessage } from '../../services/api';
import { formatCurrency } from '../../utils/format';
import { StatusBadge } from '../Shared/Badge';
import RiskValue from '../Shared/RiskValue';
import { EmptyState, ErrorState, LoadingState } from '../Shared/StateMessage';
import './RecentClaims.css';

function ClaimsTable({ claims }) {
  return (
    <div className="recent-claims-table-wrapper">
      <table className="recent-claims-table">
        <thead>
          <tr>
            <th scope="col">Claim</th>
            <th scope="col">Patient</th>
            <th scope="col" className="recent-claims-col-diagnosis">Diagnosis</th>
            <th scope="col" className="recent-claims-number">Amount</th>
            <th scope="col">Risk</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {claims.map((claim) => (
            <tr key={claim.id}>
              <td translate="no">
                <Link to={`/claims/${claim.id}`} className="record-link">
                  {claim.claim_number || 'Unnumbered claim'}
                </Link>
              </td>
              <td className="recent-claims-patient">{claim.patient_name || '—'}</td>
              <td className="recent-claims-col-diagnosis recent-claims-diagnosis" title={claim.diagnosis || undefined}>
                {claim.diagnosis || '—'}
              </td>
              <td className="recent-claims-number recent-claims-amount tabular">{formatCurrency(claim.treatment_cost)}</td>
              <td><RiskValue score={claim.risk_score} /></td>
              <td><StatusBadge status={claim.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function RecentClaims({ data, error, onRetry }) {
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
    <section className="recent-claims" id="recent-claims-table" aria-labelledby="recent-claims-title">
      <div className="section-head">
        <h2 id="recent-claims-title">Latest claims</h2>
        <Link to="/claims" className="text-link" id="view-all-claims-btn">View all claims</Link>
      </div>
      {body}
    </section>
  );
}
