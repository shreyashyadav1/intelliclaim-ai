import { useCallback, useState } from 'react';
import { useParams } from 'react-router-dom';
import ClaimDetail from '../components/Claims/ClaimDetail';
import PageHeader from '../components/Shared/PageHeader';
import { ErrorState, LoadingState } from '../components/Shared/StateMessage';
import { useApiQuery } from '../hooks/useApiQuery';
import { claimsApi, getErrorMessage, validationApi } from '../services/api';

const IDLE_VALIDATION = { running: false, result: null, error: null };
const BACK = { to: '/claims', label: 'All claims' };

function ClaimDetailView({ id }) {
  const loadClaim = useCallback(() => claimsApi.get(id), [id]);
  const claim = useApiQuery(loadClaim);
  const [statusUpdate, setStatusUpdate] = useState({ pending: null, error: null });
  const [validation, setValidation] = useState(IDLE_VALIDATION);

  const handleUpdateStatus = async (status) => {
    setStatusUpdate({ pending: status, error: null });
    try {
      const updated = await claimsApi.update(id, { status });
      claim.setData(updated);
      setStatusUpdate({ pending: null, error: null });
    } catch (err) {
      setStatusUpdate({
        pending: null,
        error: getErrorMessage(err, { 401: 'Changing a claim status is disabled on the public demo.' }),
      });
    }
  };

  const handleValidate = async () => {
    setValidation({ running: true, result: null, error: null });
    try {
      const result = await validationApi.validate(id);
      setValidation({ running: false, result, error: null });
      // Validation stores the new score and flags (and may flag the claim), so reload it.
      claim.refetch();
    } catch (err) {
      setValidation({ running: false, result: null, error: getErrorMessage(err) });
    }
  };

  if (claim.error) {
    return (
      <>
        <PageHeader title="Claim" back={BACK} />
        {claim.error.status === 404
          ? <ErrorState title="Claim not found" message="It may have been deleted, or the link is incorrect. Find it again in the claims list." />
          : <ErrorState title="Couldn't load this claim" message={getErrorMessage(claim.error)} onRetry={claim.refetch} />}
      </>
    );
  }
  if (!claim.data) {
    return (
      <>
        <PageHeader title="Claim" back={BACK} />
        <LoadingState label="Loading claim…" />
      </>
    );
  }

  return (
    <ClaimDetail
      claim={claim.data}
      pendingStatus={statusUpdate.pending}
      statusError={statusUpdate.error}
      onUpdateStatus={handleUpdateStatus}
      onDismissStatusError={() => setStatusUpdate({ pending: null, error: null })}
      validation={validation}
      onValidate={handleValidate}
      onDismissValidationError={() => setValidation(IDLE_VALIDATION)}
    />
  );
}

export default function ClaimDetailPage() {
  const { id } = useParams();
  return (
    <div id="claim-detail-page">
      {/* Keyed so status and validation state never carry over to another claim. */}
      <ClaimDetailView key={id} id={id} />
    </div>
  );
}
