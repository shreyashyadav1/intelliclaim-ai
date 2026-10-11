import { useCallback, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Flag, Loader2, ShieldCheck, XCircle } from 'lucide-react';
import { useApiQuery } from '../../hooks/useApiQuery';
import { claimsApi, documentsApi, getErrorMessage } from '../../services/api';
import { formatScore, riskColor, riskLevel } from '../../utils/format';
import { CLAIM_FIELDS } from '../../utils/trace';
import { StatusBadge } from '../Shared/Badge';
import Notice from '../Shared/Notice';
import PageHeader from '../Shared/PageHeader';
import RiskScale from '../Shared/RiskScale';
import FieldSheet from '../Trace/FieldSheet';
import SourceDocument from '../Trace/SourceDocument';
import { useTrace } from '../Trace/useTrace';
import ValidationSummary from './ValidationSummary';
import './ClaimDetail.css';

const STATUS_ACTIONS = [
  { status: 'approved', label: 'Approve', icon: CheckCircle2, id: 'approve-claim-btn' },
  { status: 'rejected', label: 'Reject', icon: XCircle, id: 'reject-claim-btn' },
  { status: 'flagged', label: 'Flag', icon: Flag, id: 'flag-claim-btn' },
];

const FIELD_LABELS = Object.fromEntries(CLAIM_FIELDS.map((field) => [field.key, field.label]));
const LEVEL_WORDS = { high: 'High risk', medium: 'Medium risk', low: 'Low risk' };
const NO_DOCUMENTS = { documents: [] };

/** The claim's documents in the order they were attached, processed ones first. */
function orderDocuments(documents, ids) {
  const position = (doc) => ids.indexOf(doc.id);
  return [...documents].sort((a, b) => {
    const failed = (doc) => (doc.processing_status === 'processed' ? 0 : 1);
    return failed(a) - failed(b) || position(a) - position(b);
  });
}

/** Source documents of the claim, with the selected one's full text. */
function useClaimSource(claimId, documentIds) {
  const hasDocuments = documentIds.length > 0;
  const loadDocuments = useCallback(
    () => (hasDocuments ? claimsApi.getDocuments(claimId) : Promise.resolve(NO_DOCUMENTS)),
    [claimId, hasDocuments],
  );
  const list = useApiQuery(loadDocuments);
  const documents = useMemo(
    () => (list.data ? orderDocuments(list.data.documents ?? [], documentIds) : null),
    [list.data, documentIds],
  );

  const [chosenId, setChosenId] = useState(null);
  const selectedId = documents?.some((doc) => doc.id === chosenId) ? chosenId : documents?.[0]?.id ?? null;

  const loadDocument = useCallback(
    () => (selectedId ? documentsApi.get(selectedId) : Promise.resolve(null)),
    [selectedId],
  );
  const full = useApiQuery(loadDocument);

  return { list, documents, selectedId, setSelectedId: setChosenId, full };
}

function DecisionButtons({ claim, pendingStatus, validating, onUpdateStatus, onValidate }) {
  const busy = Boolean(pendingStatus) || validating;
  return (
    <>
      {STATUS_ACTIONS.map(({ status, label, icon: Icon, id }) => (
        <button
          key={status}
          type="button"
          className={`btn btn-secondary decision-btn decision-btn--${status}`}
          onClick={() => onUpdateStatus(status)}
          disabled={busy || claim.status === status}
          id={id}
        >
          {pendingStatus === status
            ? <Loader2 size={16} className="spin" aria-hidden="true" />
            : <Icon size={16} aria-hidden="true" />}
          {pendingStatus === status ? 'Saving…' : label}
        </button>
      ))}
      <button type="button" className="btn btn-primary" onClick={onValidate} disabled={busy} id="validate-claim-btn">
        {validating ? <Loader2 size={16} className="spin" aria-hidden="true" /> : <ShieldCheck size={16} aria-hidden="true" />}
        {validating ? 'Validating…' : 'Validate'}
      </button>
    </>
  );
}

function RiskSection({ claim, validation }) {
  const flags = claim.risk_flags ?? [];
  const level = riskLevel(claim.risk_score);
  return (
    <section className="risk-section" aria-labelledby="risk-heading">
      <div className="section-head">
        <h2 id="risk-heading">Risk</h2>
        <p className="risk-readout">
          <span className="risk-readout-score tabular">Score: {formatScore(claim.risk_score)}</span>
          <span className="risk-readout-level" style={{ color: riskColor(claim.risk_score) }}>{LEVEL_WORDS[level]}</span>
        </p>
      </div>
      <RiskScale score={claim.risk_score} label="Risk score" />

      {validation.result ? (
        <ValidationSummary result={validation.result} />
      ) : flags.length > 0 ? (
        <ul className="risk-flags" role="list">
          {flags.map((flag, index) => (
            <li key={index} className="risk-flag">
              <AlertTriangle size={14} aria-hidden="true" className="risk-flag-icon" />
              <span className="risk-flag-text">{flag}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="risk-empty">
          No risk flags recorded. Validate the claim to score it against the billing, date, duplicate and AI
          review checks.
        </p>
      )}
    </section>
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
  const documentIds = useMemo(() => claim.document_ids ?? [], [claim.document_ids]);
  const source = useClaimSource(claim.id, documentIds);
  const fields = useMemo(
    () => CLAIM_FIELDS.map((field) => ({ ...field, value: claim[field.key] })),
    [claim],
  );
  const text = source.full.data
    ? (source.full.data.extracted_text ?? source.full.data.extracted_text_preview ?? '')
    : null;
  const { trace, activeKey, preview, locate, sheetRef } = useTrace(text, fields);

  // extraction_confidence is the share of the eleven claim fields that extraction found.
  const completeness = claim.extraction_confidence;
  const description = [claim.patient_name, claim.diagnosis].filter(Boolean).join(', ');

  let sourceError = null;
  if (source.list.error) sourceError = getErrorMessage(source.list.error);
  else if (source.full.error) sourceError = getErrorMessage(source.full.error);

  const emptySource = source.documents && source.documents.length === 0 && (
    <>
      <p className="state-title">No source document is linked to this claim</p>
      <p className="state-body">
        Documents are linked when they are extracted. <Link to="/documents">Open Documents</Link> to upload
        one and extract it into this claim.
      </p>
    </>
  );

  return (
    <div className="claim-detail" id="claim-detail">
      <PageHeader
        identifier
        title={claim.claim_number || 'Unnumbered claim'}
        back={{ to: '/claims', label: 'All claims' }}
        meta={<StatusBadge status={claim.status} />}
        description={description || undefined}
        actions={(
          <DecisionButtons
            claim={claim}
            pendingStatus={pendingStatus}
            validating={validation.running}
            onUpdateStatus={onUpdateStatus}
            onValidate={onValidate}
          />
        )}
      />

      {(statusError || validation.error) && (
        <div className="claim-detail-notices">
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
        </div>
      )}

      <div className="trace-layout">
        <div className="trace-layout-source">
          <SourceDocument
            documents={source.documents}
            selectedId={source.selectedId}
            onSelect={source.setSelectedId}
            document={source.full.data}
            loading={!source.documents || (Boolean(source.selectedId) && source.full.loading && !source.full.data)}
            error={sourceError}
            onRetry={source.list.error ? source.list.refetch : source.full.refetch}
            empty={emptySource}
            trace={trace}
            activeKey={activeKey}
            onHover={preview}
            labels={FIELD_LABELS}
            sheetRef={sheetRef}
          />
        </div>

        <div className="trace-layout-aside">
          <FieldSheet
            title="Claim fields"
            fields={fields}
            trace={trace}
            completeness={typeof completeness === 'number' ? completeness : undefined}
            activeKey={activeKey}
            onActivate={preview}
            onLocate={locate}
          />
          <RiskSection claim={claim} validation={validation} />
        </div>
      </div>
    </div>
  );
}
