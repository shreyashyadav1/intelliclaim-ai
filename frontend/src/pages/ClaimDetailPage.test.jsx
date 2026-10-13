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
            ai_review: { ai_summary: 'Cost is high for an outpatient procedure.' },
            source: 'mock',
          },
        };
      },
    });
    const { user } = renderClaim();

    await user.click(await screen.findByRole('button', { name: 'Validate' }));

    expect(await screen.findByText('Cost is high for an outpatient procedure.')).toBeInTheDocument();
    expect(screen.getByText('High risk · 72.5')).toBeInTheDocument();
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

  it('shows a not-found message instead of a sample claim', async () => {
    mockApi({ 'GET /claims/clm-1': { status: 404, data: { detail: 'Claim not found' } } });
    renderClaim();

    expect(await screen.findByText('Claim not found')).toBeInTheDocument();
    expect(screen.queryByText('James Williams')).not.toBeInTheDocument();
  });
});
