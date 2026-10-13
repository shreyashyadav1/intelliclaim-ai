import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, RefreshCw, Shield, ShieldCheck } from 'lucide-react';
import Badge from '../components/Shared/Badge';
import Notice from '../components/Shared/Notice';
import { EmptyState, ErrorState, LoadingState } from '../components/Shared/StateMessage';
import { useApiQuery } from '../hooks/useApiQuery';
import { claimsApi, getErrorMessage, validationApi } from '../services/api';
import { formatCurrency, formatScore, riskColor } from '../utils/format';
import './ValidationPage.css';

// GET /validate/flagged and GET /claims both cap `limit` at 100.
const PAGE_SIZE = 100;
const loadFlagged = () => validationApi.getFlagged({ limit: PAGE_SIZE });

const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;

function describeBatch(results, pendingTotal) {
  const failed = results.filter((result) => result.error).length;
  const validated = results.length - failed;
  const highRisk = results.filter((result) => result.risk_level === 'high').length;

  const parts = [`Validated ${plural(validated, 'pending claim')}; ${highRisk} high risk.`];
  if (failed > 0) parts.push(`${plural(failed, 'claim')} could not be validated.`);
  if (pendingTotal > results.length) {
    parts.push(`Only the ${results.length} most recent of ${pendingTotal} pending claims were included.`);
  }
  if (results.some((result) => result.source === 'mock')) parts.push('AI review used the mock LLM.');
  return { tone: failed > 0 ? 'error' : 'success', message: parts.join(' ') };
}

function FlaggedClaimCard({ claim }) {
  const color = riskColor(claim.risk_score);
  const flags = claim.risk_flags ?? [];

  return (
    <div className="glass-card flagged-claim-card" id={`flagged-${claim.id}`}>
      <div className="flagged-claim-header">
        <div className="flagged-claim-left">
          <AlertTriangle size={18} style={{ color, flexShrink: 0 }} />
          <Link to={`/claims/${claim.id}`} className="flagged-claim-number">
            {claim.claim_number || 'Unnumbered claim'}
          </Link>
          <span className="flagged-claim-patient">{claim.patient_name || '—'}</span>
          <Badge variant={claim.status}>{claim.status}</Badge>
        </div>
        <div className="flagged-claim-right">
          <span className="flagged-claim-cost">{formatCurrency(claim.treatment_cost)}</span>
          <span className="flagged-risk-pill" style={{ color, background: `${color}15` }}>
            Risk: {formatScore(claim.risk_score)}
          </span>
        </div>
      </div>
      {flags.length > 0 && (
        <div className="flagged-flags">
          {flags.map((flag, index) => (
            <span key={index} className="flagged-flag-tag">{flag}</span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ValidationPage() {
  const flagged = useApiQuery(loadFlagged);
  const [batch, setBatch] = useState({ running: false, notice: null });

  const handleValidatePending = async () => {
    setBatch({ running: true, notice: null });
    try {
      const pending = await claimsApi.list({ status: 'pending', limit: PAGE_SIZE });
      const ids = (pending.claims ?? []).map((claim) => claim.id);
      if (ids.length === 0) {
        setBatch({ running: false, notice: { tone: 'info', message: 'There are no pending claims to validate.' } });
        return;
      }
      const { results } = await validationApi.batchValidate(ids);
      setBatch({ running: false, notice: describeBatch(results, pending.total ?? ids.length) });
      flagged.refetch();
    } catch (err) {
      setBatch({
        running: false,
        notice: { tone: 'error', message: `Batch validation failed: ${getErrorMessage(err)}` },
      });
    }
  };

  const claims = flagged.data?.claims;

  let content;
  if (flagged.error) {
    content = (
      <div className="glass-card validation-state-card">
        <ErrorState title="Couldn't load flagged claims" message={getErrorMessage(flagged.error)} onRetry={flagged.refetch} />
      </div>
    );
  } else if (!claims) {
    content = (
      <div className="glass-card validation-state-card">
        <LoadingState label="Loading flagged claims…" />
      </div>
    );
  } else if (claims.length === 0) {
    content = (
      <div className="glass-card validation-state-card">
        <EmptyState icon={ShieldCheck} title="No flagged claims">
          Claims appear here when they are flagged or score 30 or more. Validate pending claims to check them.
        </EmptyState>
      </div>
    );
  } else {
    content = (
      <div className="flagged-claims-list">
        {claims.map((claim) => <FlaggedClaimCard key={claim.id} claim={claim} />)}
      </div>
    );
  }

  return (
    <div className="page-enter" id="validation-page">
      <div className="validation-toolbar">
        <div className="validation-toolbar-left">
          <Shield size={22} color="var(--accent-primary)" />
          <h2 className="validation-title">Risk & Validation</h2>
          {flagged.data && <Badge variant="danger">{flagged.data.total ?? claims.length} flagged</Badge>}
        </div>
        <div className="validation-toolbar-actions">
          <button
            type="button"
            onClick={handleValidatePending}
            disabled={batch.running}
            className="validation-refresh-btn validation-refresh-btn--accent"
            id="validate-pending-btn"
          >
            <ShieldCheck size={14} /> {batch.running ? 'Validating…' : 'Validate pending'}
          </button>
          <button
            type="button"
            onClick={flagged.refetch}
            disabled={flagged.loading}
            className="validation-refresh-btn"
            id="refresh-flagged-btn"
          >
            <RefreshCw size={14} className={flagged.loading ? 'is-spinning' : ''} /> Refresh
          </button>
        </div>
      </div>

      {batch.notice && (
        <Notice tone={batch.notice.tone} onDismiss={() => setBatch({ running: false, notice: null })}>
          {batch.notice.message}
        </Notice>
      )}

      {content}
    </div>
  );
}
