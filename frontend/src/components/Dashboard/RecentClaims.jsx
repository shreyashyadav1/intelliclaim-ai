import { useNavigate } from 'react-router-dom';
import { ExternalLink } from 'lucide-react';
import Badge from '../Shared/Badge';
import './RecentClaims.css';

const demoClaims = [
  { id: 'clm-1', claim_number: 'CLM-2026-10001', patient_name: 'Sarah Johnson', diagnosis: 'ACL Tear (S83.5)', treatment_cost: 34500, status: 'approved', risk_score: 15, created_at: '2026-06-15' },
  { id: 'clm-2', claim_number: 'CLM-2026-10002', patient_name: 'Michael Chen', diagnosis: 'Type 2 Diabetes (E11.9)', treatment_cost: 12800, status: 'pending', risk_score: 22, created_at: '2026-06-14' },
  { id: 'clm-3', claim_number: 'CLM-2026-10003', patient_name: 'Emily Rodriguez', diagnosis: 'Acute Appendicitis (K35.80)', treatment_cost: 28900, status: 'approved', risk_score: 8, created_at: '2026-06-13' },
  { id: 'clm-4', claim_number: 'CLM-2026-10004', patient_name: 'James Williams', diagnosis: 'Lumbar Disc Herniation (M51.16)', treatment_cost: 67200, status: 'flagged', risk_score: 72, created_at: '2026-06-12' },
  { id: 'clm-5', claim_number: 'CLM-2026-10005', patient_name: 'Amanda Thompson', diagnosis: 'Knee Replacement (Z96.651)', treatment_cost: 89500, status: 'pending', risk_score: 45, created_at: '2026-06-11' },
  { id: 'clm-6', claim_number: 'CLM-2026-10006', patient_name: 'Robert Davis', diagnosis: 'Coronary Artery Disease (I25.10)', treatment_cost: 156000, status: 'flagged', risk_score: 85, created_at: '2026-06-10' },
  { id: 'clm-7', claim_number: 'CLM-2026-10007', patient_name: 'Lisa Garcia', diagnosis: 'Cholecystitis (K81.0)', treatment_cost: 19200, status: 'approved', risk_score: 5, created_at: '2026-06-09' },
];

function getRiskColor(score) {
  if (score >= 60) return '#ef4444';
  if (score >= 30) return '#f59e0b';
  return '#10b981';
}

export default function RecentClaims({ data }) {
  const navigate = useNavigate();
  const claims = data && data.length > 0 ? data : demoClaims;

  return (
    <div className="recent-claims glass-card" id="recent-claims-table">
      <div className="recent-claims-header">
        <h3 className="recent-claims-title">Recent Claims</h3>
        <button className="recent-claims-view-all" onClick={() => navigate('/claims')} id="view-all-claims-btn">
          View All <ExternalLink size={14} />
        </button>
      </div>
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
            {claims.slice(0, 7).map((claim) => (
              <tr key={claim.id} onClick={() => navigate(`/claims/${claim.id}`)} className="recent-claims-row">
                <td className="claim-number-cell">{claim.claim_number}</td>
                <td>{claim.patient_name}</td>
                <td className="diagnosis-cell">{claim.diagnosis}</td>
                <td className="amount-cell">${claim.treatment_cost?.toLocaleString()}</td>
                <td><Badge variant={claim.status}>{claim.status}</Badge></td>
                <td>
                  <span className="risk-score-badge" style={{ color: getRiskColor(claim.risk_score), background: `${getRiskColor(claim.risk_score)}15` }}>
                    {claim.risk_score}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
