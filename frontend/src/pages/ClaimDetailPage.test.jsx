import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { mockApi } from '../test/mockApi';
import { renderWithRouter } from '../test/render';
import ClaimDetailPage from './ClaimDetailPage';

const claim = {
  id: 'clm-1',
  claim_number: 'CLM-2026-00001',
  policy_number: 'POL-2026-00001',
  patient_name: 'Dana Whitfield',
  diagnosis: 'Knee arthroscopy',
  treatment_cost: 72000,
  hospital_name: 'Lakeside Medical Center',
  status: 'pending',
  risk_score: 0,
  risk_flags: [],
  extraction_confidence: 0.9,
};

const renderClaim = () => renderWithRouter(<ClaimDetailPage />, { route: '/claims/clm-1', path: '/claims/:id' });

describe('ClaimDetailPage', () => {
  it('runs validation and shows the risk result', async () => {
    let current = claim;
    const requests = mockApi({
      'GET /claims/clm-1': () => ({ data: current }),
      'POST /validate/clm-1': () => {
        current = { ...claim, status: 'flagged', risk_score: 72.5, risk_flags: ['Treatment cost exceeds $50,000'] };
        return {
          data: {
            claim_id: 'clm-1',
            risk_score: 72.5,
            risk_level: 'high',
            flags: [{ type: 'high_cost', description: 'Treatment cost exceeds $50,000', severity: 'medium' }],
            is_duplicate: false,
            ai_review: { ai_summary: 'Cost is high for an outpatient procedure.', status: 'mock', source: 'mock' },
          },
        };
      },
    });
    const { user } = renderClaim();

    // extraction_confidence is shown as completeness, not as a model confidence.
    expect(await screen.findByText('Completeness')).toBeInTheDocument();
    expect(screen.getByText('90%')).toBeInTheDocument();
    expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument();

    await user.click(await screen.findByRole('button', { name: 'Validate' }));

    expect(await screen.findByText('Cost is high for an outpatient procedure.')).toBeInTheDocument();
    expect(screen.getByText('High risk, score 72.5')).toBeInTheDocument();
    expect(screen.getByText('Treatment cost exceeds $50,000')).toBeInTheDocument();
    expect(screen.getByText('medium')).toBeInTheDocument();
    expect(screen.getByText('Mock AI')).toBeInTheDocument();
    // The claim is reloaded so the stored score and status are shown.
    expect(await screen.findByText('Score: 72.5')).toBeInTheDocument();
    expect(requests.filter((request) => request.url === '/claims/clm-1')).toHaveLength(2);
  });

  it('keeps the current status when an update is rejected', async () => {
    mockApi({
      'GET /claims/clm-1': { data: claim },
      'PUT /claims/clm-1': { status: 401, data: { detail: 'Admin key required' } },
    });
    const { user } = renderClaim();

    await user.click(await screen.findByRole('button', { name: 'Approve' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Changing a claim status is disabled on the public demo.');
    expect(screen.getByText('pending')).toBeInTheDocument();
    expect(screen.queryByText('approved')).not.toBeInTheDocument();
  });

  it('traces each field to the line of the source document it came from', async () => {
    const sourceDoc = { id: 'doc-1', filename: 'invoice_dana.pdf', document_class: 'invoice', processing_status: 'processed' };
    mockApi({
      'GET /claims/clm-1': { data: { ...claim, document_ids: ['doc-1'] } },
      'GET /claims/clm-1/documents': { data: { documents: [sourceDoc] } },
      'GET /documents/doc-1': {
        data: { ...sourceDoc, extracted_text: 'Patient: Dana Whitfield\nPolicy: POL-2026-00001\nTotal due: $72,000.00' },
      },
    });
    const { user } = renderClaim();

    const patientLine = await screen.findByRole('button', { name: 'Show patient name in the document: Line 1' });
    expect(screen.getByRole('button', { name: 'Show treatment cost in the document: Line 3' })).toBeInTheDocument();
    // The claim's diagnosis, hospital and claim number are not in this invoice.
    expect(screen.getAllByText('Not in this document')).toHaveLength(3);
    expect(screen.getByText('3 of 6 values found in this document.')).toBeInTheDocument();

    await user.click(patientLine);

    expect(screen.getByText('Dana Whitfield', { selector: 'mark' })).toHaveAttribute('data-active', 'true');
  });

  it('shows a not-found message instead of a sample claim', async () => {
    mockApi({ 'GET /claims/clm-1': { status: 404, data: { detail: 'Claim not found' } } });
    renderClaim();

    expect(await screen.findByText('Claim not found')).toBeInTheDocument();
    expect(screen.queryByText('James Williams')).not.toBeInTheDocument();
  });
});
