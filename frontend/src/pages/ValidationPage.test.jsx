import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { mockApi } from '../test/mockApi';
import { renderWithRouter } from '../test/render';
import ValidationPage from './ValidationPage';

const flaggedClaim = {
  id: 'clm-1',
  claim_number: 'CLM-2026-00001',
  patient_name: 'Dana Whitfield',
  treatment_cost: 72000,
  status: 'flagged',
  risk_score: 75,
  risk_flags: ['Treatment cost exceeds $50,000 threshold'],
};

describe('ValidationPage', () => {
  it('validates pending claims through POST /batch-validate and refreshes the list', async () => {
    let flaggedResponse = { claims: [], total: 0 };
    const requests = mockApi({
      'GET /validate/flagged': () => ({ data: flaggedResponse }),
      'GET /claims': { data: { claims: [{ id: 'clm-1' }, { id: 'clm-2' }], total: 2 } },
      'POST /batch-validate': () => {
        flaggedResponse = { claims: [flaggedClaim], total: 1 };
        return {
          data: {
            results: [
              { claim_id: 'clm-1', risk_score: 75, risk_level: 'high', flags: [] },
              { claim_id: 'clm-2', risk_score: 5, risk_level: 'low', flags: [] },
            ],
            total_validated: 2,
          },
        };
      },
    });
    const { user } = renderWithRouter(<ValidationPage />);

    expect(await screen.findByText('No flagged claims')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Validate pending' }));

    expect(await screen.findByText('Validated 2 pending claims; 1 high risk.')).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: 'CLM-2026-00001' })).toHaveAttribute('href', '/claims/clm-1');
    expect(screen.getByText('1 flagged')).toBeInTheDocument();

    const calls = requests.map((request) => `${request.method} ${request.url}`);
    expect(calls).toEqual([
      'GET /validate/flagged',
      'GET /claims',
      'POST /batch-validate',
      'GET /validate/flagged',
    ]);
    expect(requests[1].params).toMatchObject({ status: 'pending', limit: 100 });
    expect(requests[2].body).toEqual({ claim_ids: ['clm-1', 'clm-2'] });
  });

  it('does not call the batch endpoint when nothing is pending', async () => {
    const requests = mockApi({
      'GET /validate/flagged': { data: { claims: [flaggedClaim], total: 1 } },
      'GET /claims': { data: { claims: [], total: 0 } },
    });
    const { user } = renderWithRouter(<ValidationPage />);

    await user.click(await screen.findByRole('button', { name: 'Validate pending' }));

    expect(await screen.findByText('There are no pending claims to validate.')).toBeInTheDocument();
    expect(requests.some((request) => request.url === '/batch-validate')).toBe(false);
  });

  it('shows the error instead of sample claims when the list fails to load', async () => {
    mockApi({ 'GET /validate/flagged': { status: 503, data: { detail: 'Database unavailable' } } });
    renderWithRouter(<ValidationPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable');
    expect(screen.queryByText(/flagged$/)).not.toBeInTheDocument();
    expect(screen.queryByText('James Williams')).not.toBeInTheDocument();
  });
});
