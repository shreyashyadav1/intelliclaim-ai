import { AlertTriangle, Building2, CheckCircle, DollarSign, Flag, ShieldCheck, Stethoscope, User, XCircle } from 'lucide-react';
import { formatCurrency, formatDate, formatScore, riskColor } from '../../utils/format';
import Badge from '../Shared/Badge';
import Notice from '../Shared/Notice';
import ValidationSummary from './ValidationSummary';
import './ClaimDetail.css';

const STATUS_ACTIONS = [
  { status: 'approved', label: 'Approve', icon: CheckCircle, tone: 'success', id: 'approve-claim-btn' },
  { status: 'rejected', label: 'Reject', icon: XCircle, tone: 'danger', id: 'reject-claim-btn' },
  { status: 'flagged', label: 'Flag', icon: Flag, tone: 'warning', id: 'flag-claim-btn' },
];

function Field({ label, value, format, mono = false }) {
  const missing = value === null || value === undefined || value === '';
  return (
    <div className="card-field">
      <span className="field-label">{label}</span>
      <span className={`field-value ${mono ? 'mono' : ''}`}>{missing ? 'N/A' : format ? format(value) : value}</span>
    </div>
  );
}

export default function ClaimDetail({
  claim,
  pendingStatus,
  statusError,
  onUpdateStatus,
  onDismissStatusError,
  validation,
  onValidate,
  onDismissValidationError,
}) {
  const busy = Boolean(pendingStatus) || validation.running;
  const confidence = claim.extraction_confidence;
  const hasConfidence = typeof confidence === 'number';
  const flags = claim.risk_flags ?? [];
  const color = riskColor(claim.risk_score);

  return (
    <div className="claim-detail" id="claim-detail">
      <div className="claim-detail-header glass-card">
        <div className="claim-detail-header-left">
          <h2>{claim.claim_number || 'Unnumbered claim'}</h2>
          <Badge variant={claim.status}>{claim.status}</Badge>
        </div>
        <div className="claim-detail-actions">
          {STATUS_ACTIONS.map(({ status, label, icon: Icon, tone, id }) => (
            <button
              key={status}
              type="button"
              className={`action-btn action-btn--${tone}`}
              onClick={() => onUpdateStatus(status)}
              disabled={busy || claim.status === status}
              id={id}
            >
              <Icon size={16} /> {pendingStatus === status ? 'Saving…' : label}
            </button>
          ))}
          <button
            type="button"
            className="action-btn action-btn--accent"
            onClick={onValidate}
            disabled={busy}
            id="validate-claim-btn"
          >
            <ShieldCheck size={16} /> {validation.running ? 'Validating…' : 'Validate'}
          </button>
        </div>
      </div>

      {statusError && (
        <Notice tone="error" onDismiss={onDismissStatusError}>
          {statusError}
        </Notice>
      )}
      {validation.error && (
        <Notice tone="error" onDismiss={onDismissValidationError}>
          Validation failed: {validation.error}
        </Notice>
      )}

      <div className="claim-detail-grid">
        <div className="claim-info-card glass-card">
          <div className="card-section-header">
            <User size={16} /> Patient Information
          </div>
          <Field label="Name" value={claim.patient_name} />
          <Field label="Policy #" value={claim.policy_number} mono />
          <Field label="Service Date" value={claim.date_of_service} format={formatDate} />
        </div>

        <div className="claim-info-card glass-card">
          <div className="card-section-header">
            <Stethoscope size={16} /> Treatment Details
          </div>
          <Field label="Diagnosis" value={claim.diagnosis} />
          <Field label="Admission" value={claim.date_of_admission} format={formatDate} />
          <Field label="Discharge" value={claim.date_of_discharge} format={formatDate} />
        </div>

        <div className="claim-info-card glass-card">
          <div className="card-section-header">
            <Building2 size={16} /> Hospital Information
          </div>
          <Field label="Hospital" value={claim.hospital_name} />
          <Field label="Address" value={claim.hospital_address} />
          <Field label="Provider ID" value={claim.provider_id} mono />
        </div>

        <div className="claim-info-card glass-card">
          <div className="card-section-header">
            <DollarSign size={16} /> Cost & Confidence
          </div>
          <div className="card-field">
            <span className="field-label">Treatment Cost</span>
            <span className="field-value cost">{formatCurrency(claim.treatment_cost)}</span>
          </div>
          <div className="card-field">
            <span className="field-label">AI Confidence</span>
            {hasConfidence ? (
              <div className="confidence-bar-wrapper">
                <div className="confidence-bar">
                  <div className="confidence-fill" style={{ width: `${confidence * 100}%` }} />
                </div>
                <span className="confidence-pct">{(confidence * 100).toFixed(0)}%</span>
              </div>
            ) : (
              <span className="field-value">N/A</span>
            )}
          </div>
        </div>
      </div>

      <div className="risk-assessment glass-card">
        <div className="card-section-header">
          <AlertTriangle size={16} style={{ color }} /> Risk Assessment
          <span className="risk-score-display" style={{ color }}>
            Score: {formatScore(claim.risk_score)}
          </span>
        </div>
        {validation.result ? (
          <ValidationSummary result={validation.result} />
        ) : flags.length > 0 ? (
          <div className="risk-flags-list">
            {flags.map((flag, index) => (
              <div key={index} className="risk-flag-item">
                <AlertTriangle size={14} style={{ color }} />
                <span>{flag}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="risk-assessment-empty">
            No risk flags recorded. Run validation to score this claim against the billing, date,
            duplicate and AI review checks.
          </p>
        )}
      </div>
    </div>
  );
}
