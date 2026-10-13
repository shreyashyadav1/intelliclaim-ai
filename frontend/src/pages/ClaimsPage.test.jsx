import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { mockApi } from '../test/mockApi';
import { renderWithRouter } from '../test/render';
import ClaimsPage from './ClaimsPage';

const claim = {
  id: 'clm-1',
  claim_number: 'CLM-2026-00001',
  policy_number: 'POL-2026-00001',
  patient_name: 'Dana Whitfield',
  diagnosis: 'Knee arthroscopy',
  treatment_cost: 18250,
  status: 'pending',
  risk_score: 12,
  created_at: '2026-09-01T10:00:00Z',
};

describe('ClaimsPage', () => {
  it('shows the API error with a retry instead of sample claims', async () => {
    let failing = true;
    const requests = mockApi({
      'GET /claims': () => (failing
        ? { status: 500, data: { detail: 'Database connection lost' } }
        : { data: { claims: [claim], total: 1 } }),
    });
    const { user } = renderWithRouter(<ClaimsPage />, { route: '/claims' });

    expect(await screen.findByRole('alert')).toHaveTextContent('Database connection lost');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.queryByText('Sarah Johnson')).not.toBeInTheDocument();

    failing = false;
    await user.click(screen.getByRole('button', { name: /try again/i }));

    expect(await screen.findByText('CLM-2026-00001')).toBeInTheDocument();
    expect(requests).toHaveLength(2);
  });

  it('shows an empty state when there are no claims', async () => {
    mockApi({ 'GET /claims': { data: { claims: [], total: 0 } } });
    renderWithRouter(<ClaimsPage />, { route: '/claims' });

    expect(await screen.findByText('No claims yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Upload a document' })).toHaveAttribute('href', '/documents');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('sends the search from the URL to the API and reports when nothing matches', async () => {
    const requests = mockApi({ 'GET /claims': { data: { claims: [], total: 0 } } });
    renderWithRouter(<ClaimsPage />, { route: '/claims?search=knee&status=flagged' });

    expect(await screen.findByText('No claims match your filters')).toBeInTheDocument();
    expect(screen.getByLabelText('Search claims')).toHaveValue('knee');
    expect(requests[0].params).toMatchObject({ search: 'knee', status: 'flagged', limit: 100 });
  });
});
