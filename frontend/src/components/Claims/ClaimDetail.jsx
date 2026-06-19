import { useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle, XCircle, Flag, User, Stethoscope, Building2, DollarSign, AlertTriangle, FileText } from 'lucide-react';
import Badge from '../Shared/Badge';
import './ClaimDetail.css';

const demoClaim = {
  id: 'clm-4',
  claim_number: 'CLM-2026-10004',
  policy_number: 'POL-2026-50004',
  patient_name: 'James Williams',
  diagnosis: 'Lumbar Disc Herniation (M51.16)',
  treatment_cost: 67200,
  hospital_name: 'Spine Care Institute',
  hospital_address: '1250 Medical Dr, Chicago, IL 60601',
  provider_id: 'NPI-1234567890',
  date_of_service: '2026-05-28',
  date_of_admission: '2026-05-27',
  date_of_discharge: '2026-06-02',
  status: 'flagged',
  risk_score: 72,
  risk_flags: ['Treatment cost exceeds $50,000 threshold', 'Potential duplicate claim detected'],
  document_ids: ['doc-4'],
  extraction_confidence: 0.92,
  created_at: '2026-06-12T11:45:00Z',
};

function getRiskColor(score) {
  if (score >= 60) return '#ef4444';
  if (score >= 30) return '#f59e0b';
  return '#10b981';
}

export default function ClaimDetail({ claim, onUpdateStatus }) {
  const navigate = useNavigate();
  const data = claim || demoClaim;

  return (
    <div className="claim-detail page-enter" id="claim-detail">
      <button className="claim-detail-back" onClick={() => navigate('/claims')} id="back-to-claims">
        <ArrowLeft size={18} /> Back to Claims
      </button>

      <div className="claim-detail-header glass-card">
        <div className="claim-detail-header-left">
          <h2>{data.claim_number}</h2>
          <Badge variant={data.status}>{data.status}</Badge>
        </div>
        <div className="claim-detail-actions">
          <button className="action-btn action-btn--success" onClick={() => onUpdateStatus?.(data.id, 'approved')} id="approve-claim-btn">
            <CheckCircle size={16} /> Approve
          </button>
          <button className="action-btn action-btn--danger" onClick={() => onUpdateStatus?.(data.id, 'rejected')} id="reject-claim-btn">
            <XCircle size={16} /> Reject
          </button>
          <button className="action-btn action-btn--warning" onClick={() => onUpdateStatus?.(data.id, 'flagged')} id="flag-claim-btn">
            <Flag size={16} /> Flag
          </button>
        </div>
      </div>

      <div className="claim-detail-grid">
        <div className="claim-info-card glass-card">
          <div className="card-section-header">
            <User size={16} /> Patient Information
          </div>
          <div className="card-field"><span className="field-label">Name</span><span className="field-value">{data.patient_name}</span></div>
          <div className="card-field"><span className="field-label">Policy #</span><span className="field-value mono">{data.policy_number}</span></div>
          <div className="card-field"><span className="field-label">Service Date</span><span className="field-value">{data.date_of_service || 'N/A'}</span></div>
        </div>

        <div className="claim-info-card glass-card">
          <div className="card-section-header">
            <Stethoscope size={16} /> Treatment Details
          </div>
          <div className="card-field"><span className="field-label">Diagnosis</span><span className="field-value">{data.diagnosis}</span></div>
          <div className="card-field"><span className="field-label">Admission</span><span className="field-value">{data.date_of_admission || 'N/A'}</span></div>
          <div className="card-field"><span className="field-label">Discharge</span><span className="field-value">{data.date_of_discharge || 'N/A'}</span></div>
        </div>

        <div className="claim-info-card glass-card">
          <div className="card-section-header">
            <Building2 size={16} /> Hospital Information
          </div>
          <div className="card-field"><span className="field-label">Hospital</span><span className="field-value">{data.hospital_name}</span></div>
          <div className="card-field"><span className="field-label">Address</span><span className="field-value">{data.hospital_address || 'N/A'}</span></div>
          <div className="card-field"><span className="field-label">Provider ID</span><span className="field-value mono">{data.provider_id || 'N/A'}</span></div>
        </div>

        <div className="claim-info-card glass-card">
          <div className="card-section-header">
            <DollarSign size={16} /> Cost & Confidence
          </div>
          <div className="card-field">
            <span className="field-label">Treatment Cost</span>
            <span className="field-value cost">${data.treatment_cost?.toLocaleString()}</span>
          </div>
          <div className="card-field">
            <span className="field-label">AI Confidence</span>
            <div className="confidence-bar-wrapper">
              <div className="confidence-bar"><div className="confidence-fill" style={{ width: `${(data.extraction_confidence || 0) * 100}%` }} /></div>
              <span className="confidence-pct">{((data.extraction_confidence || 0) * 100).toFixed(0)}%</span>
            </div>
          </div>
        </div>
      </div>

      {data.risk_flags && data.risk_flags.length > 0 && (
        <div className="risk-assessment glass-card">
          <div className="card-section-header">
            <AlertTriangle size={16} style={{ color: getRiskColor(data.risk_score) }} /> Risk Assessment
            <span className="risk-score-display" style={{ color: getRiskColor(data.risk_score) }}>
              Score: {data.risk_score}
            </span>
          </div>
          <div className="risk-flags-list">
            {data.risk_flags.map((flag, i) => (
              <div key={i} className="risk-flag-item">
                <AlertTriangle size={14} style={{ color: getRiskColor(data.risk_score) }} />
                <span>{flag}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
