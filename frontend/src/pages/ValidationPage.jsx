import { useState, useEffect } from 'react';
import { AlertTriangle, Shield, RefreshCw } from 'lucide-react';
import Badge from '../components/Shared/Badge';
import { validationApi } from '../services/api';
import './ValidationPage.css';

const demoClaims = [
  { id: 'clm-4', claim_number: 'CLM-2026-10004', patient_name: 'James Williams', diagnosis: 'Lumbar Disc Herniation', treatment_cost: 67200, status: 'flagged', risk_score: 72, risk_flags: ['High treatment cost', 'Potential duplicate claim'] },
  { id: 'clm-6', claim_number: 'CLM-2026-10006', patient_name: 'Robert Davis', diagnosis: 'Coronary Artery Disease', treatment_cost: 156000, status: 'flagged', risk_score: 85, risk_flags: ['Very high treatment cost', 'Long hospital stay'] },
  { id: 'clm-5', claim_number: 'CLM-2026-10005', patient_name: 'Amanda Thompson', diagnosis: 'Knee Replacement', treatment_cost: 89500, status: 'pending', risk_score: 45, risk_flags: ['High treatment cost'] },
  { id: 'clm-10', claim_number: 'CLM-2026-10010', patient_name: 'Christopher Lee', diagnosis: 'Pneumonia', treatment_cost: 8900, status: 'rejected', risk_score: 55, risk_flags: ['Missing provider ID', 'Suspicious billing'] },
];

function getRiskColor(score) {
  if (score >= 60) return '#ef4444';
  if (score >= 30) return '#f59e0b';
  return '#10b981';
}

export default function ValidationPage() {
  const [flagged, setFlagged] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchFlagged();
  }, []);

  const fetchFlagged = async () => {
    setLoading(true);
    try {
      const result = await validationApi.getFlagged();
      setFlagged(result.claims || []);
    } catch {
      setFlagged(demoClaims);
    } finally {
      setLoading(false);
    }
  };

  const claims = flagged.length > 0 ? flagged : demoClaims;

  return (
    <div className="page-enter" id="validation-page">
      <div className="validation-toolbar">
        <div className="validation-toolbar-left">
          <Shield size={22} color="var(--accent-primary)" />
          <h2 className="validation-title">Risk & Validation</h2>
          <Badge variant="danger">{claims.length} flagged</Badge>
        </div>
        <button
          onClick={fetchFlagged}
          className="validation-refresh-btn"
          id="refresh-flagged-btn"
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {claims.map((claim) => (
          <div key={claim.id} className="glass-card flagged-claim-card" id={`flagged-${claim.id}`}>
            <div className="flagged-claim-header">
              <div className="flagged-claim-left">
                <AlertTriangle size={18} style={{ color: getRiskColor(claim.risk_score), flexShrink: 0 }} />
                <span className="flagged-claim-number">{claim.claim_number}</span>
                <span className="flagged-claim-patient">{claim.patient_name}</span>
                <Badge variant={claim.status}>{claim.status}</Badge>
              </div>
              <div className="flagged-claim-right">
                <span className="flagged-claim-cost">${claim.treatment_cost?.toLocaleString()}</span>
                <span
                  className="flagged-risk-pill"
                  style={{
                    color: getRiskColor(claim.risk_score),
                    background: `${getRiskColor(claim.risk_score)}15`,
                  }}
                >
                  Risk: {claim.risk_score}
                </span>
              </div>
            </div>
            {claim.risk_flags && claim.risk_flags.length > 0 && (
              <div className="flagged-flags">
                {claim.risk_flags.map((flag, i) => (
                  <span key={i} className="flagged-flag-tag">{flag}</span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
