import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Loader2, RefreshCw, ShieldCheck } from 'lucide-react';
import Badge, { StatusBadge } from '../components/Shared/Badge';
import Notice from '../components/Shared/Notice';
import PageHeader from '../components/Shared/PageHeader';
import RiskScale from '../components/Shared/RiskScale';
import { EmptyState, ErrorState, LoadingState } from '../components/Shared/StateMessage';
import { useApiQuery } from '../hooks/useApiQuery';
import { claimsApi, getErrorMessage, validationApi } from '../services/api';
import { formatCurrency, formatScore, getFlagThreshold, HIGH_RISK_THRESHOLD, riskColor, riskLevel } from '../utils/format';
import './ValidationPage.css';

// GET /validate/flagged and GET /claims both cap `limit` at 100.
const PAGE_SIZE = 100;
const loadFlagged = () => validationApi.getFlagged({ limit: PAGE_SIZE });
const LEVEL_WORDS = { high: 'High', medium: 'Medium', low: 'Low' };

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
  // Validation results report where the AI review came from in ai_review.source.
  if (results.some((result) => (result.ai_review?.source ?? result.source) === 'mock')) {
    parts.push('AI review used the mock LLM.');
  }
  return { tone: failed > 0 ? 'error' : 'success', message: parts.join(' ') };
}

/** Where the listed claims fall on the risk bands, one tick per claim. */
function QueueSpread({ claims }) {
  const scores = claims.map((claim) => Number(claim.risk_score) || 0);
  const high = scores.filter((score) => score >= HIGH_RISK_THRESHOLD).length;
  return (
    <div className="queue-spread">
      <RiskScale
        markers={scores}
        description={`${plural(scores.length, 'listed claim')} on the risk bands: ${high} high risk, ${scores.length - high} below ${HIGH_RISK_THRESHOLD}.`}
      />
    </div>
  );
}

function FlaggedClaimRow({ claim }) {
  const color = riskColor(claim.risk_score);
  const flags = claim.risk_flags ?? [];

  return (
    <li className="flagged-row" id={`flagged-${claim.id}`}>
      <div className="flagged-row-claim">
        <Link to={`/claims/${claim.id}`} className="record-link" translate="no">
          {claim.claim_number || 'Unnumbered claim'}
        </Link>
        <span className="flagged-row-patient">{claim.patient_name || '—'}</span>
        <StatusBadge status={claim.status} />
      </div>
      <ul className="flagged-row-flags" role="list" aria-label="Risk flags">
        {flags.length > 0 ? flags.map((flag, index) => (
          <li key={index} className="flag-chip">
            <AlertTriangle size={12} aria-hidden="true" />
            {flag}
          </li>
        )) : <li className="flag-chip flag-chip--none">No flags recorded</li>}
      </ul>
      <span className="flagged-row-amount tabular">{formatCurrency(claim.treatment_cost)}</span>
      <span className="flagged-row-risk">
        <span className="flagged-risk tabular" style={{ color }}>Risk: {formatScore(claim.risk_score)}</span>
        <span className="flagged-risk-band">{LEVEL_WORDS[riskLevel(claim.risk_score)]}</span>
      </span>
    </li>
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
  const threshold = flagged.data?.flag_threshold ?? getFlagThreshold();

  let content;
  if (flagged.error) {
    content = <ErrorState title="Couldn't load flagged claims" message={getErrorMessage(flagged.error)} onRetry={flagged.refetch} />;
  } else if (!claims) {
    content = <LoadingState label="Loading flagged claims…" />;
  } else if (claims.length === 0) {
    content = (
      <EmptyState icon={ShieldCheck} title="No flagged claims">
        Claims appear here when they are flagged or score {formatScore(threshold)} or more. Validate pending claims
        to check them.
      </EmptyState>
    );
  } else {
    content = (
      <>
        <QueueSpread claims={claims} />
        <ul className="flagged-rows" role="list">
          {claims.map((claim) => <FlaggedClaimRow key={claim.id} claim={claim} />)}
        </ul>
      </>
    );
  }

  return (
    <div id="validation-page">
      <PageHeader
        title="Validation"
        description="Claims that were flagged or scored at or above the flag threshold, highest risk first."
        meta={flagged.data && <Badge variant="warning">{flagged.data.total ?? claims.length} flagged</Badge>}
        actions={(
          <>
            <button
              type="button"
              onClick={handleValidatePending}
              disabled={batch.running}
              className="btn btn-primary"
              id="validate-pending-btn"
            >
              {batch.running ? <Loader2 size={16} className="spin" aria-hidden="true" /> : <ShieldCheck size={16} aria-hidden="true" />}
              {batch.running ? 'Validating…' : 'Validate pending'}
            </button>
            <button
              type="button"
              onClick={flagged.refetch}
              disabled={flagged.loading}
              className="btn btn-secondary"
              id="refresh-flagged-btn"
            >
              <RefreshCw size={16} className={flagged.loading ? 'spin' : ''} aria-hidden="true" /> Refresh
            </button>
          </>
        )}
      />

      {batch.notice && (
        <div className="validation-notice">
          <Notice tone={batch.notice.tone} onDismiss={() => setBatch({ running: false, notice: null })}>
            {batch.notice.message}
          </Notice>
        </div>
      )}

      {content}
    </div>
  );
}
