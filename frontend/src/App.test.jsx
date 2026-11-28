import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import App from './App';
import { mockApi } from './test/mockApi';
import { renderWithRouter } from './test/render';

// Every page except the 404 page is a React.lazy chunk. React keeps a lazy page
// once it has loaded, so each test opens a page no other test in this file opens.

const HEALTHY = { 'GET /health': { data: { status: 'ok' } } };
// The first render of a page imports its module (the dashboard's includes
// Recharts), which can outlast findBy's 1 s default on a busy CI runner.
const PAGE_LOAD = { timeout: 3000 };

const emptyOverview = {
  total_claims: 0,
  documents_processed: 0,
  claims_by_status: {},
  avg_treatment_cost: 0,
  avg_risk_score: 0,
  high_risk_count: 0,
  approval_rate: 0,
};

const claim = {
  id: 'clm-1',
  claim_number: 'CLM-2026-00001',
  policy_number: 'POL-2026-00001',
  patient_name: 'Dana Whitfield',
  diagnosis: 'Knee arthroscopy',
  treatment_cost: 18250,
  hospital_name: 'Lakeside Medical Center',
  status: 'pending',
  risk_score: 12,
  risk_flags: [],
  extraction_confidence: 0.9,
};

const mainNav = () => within(screen.getByRole('navigation', { name: 'Main' }));

describe('App routes', () => {
  it('shows the loading placeholder inside the layout, then the lazy dashboard at /', async () => {
    mockApi({
      ...HEALTHY,
      'GET /analytics/overview': { data: emptyOverview },
      'GET /analytics/claims-trend': { data: [] },
      'GET /analytics/recent-claims': { data: [] },
    });
    renderWithRouter(<App />, { route: '/' });

    // While the page chunk loads, the top bar stays and the placeholder is announced.
    expect(screen.getByRole('status')).toHaveTextContent('Loading page…');
    expect(mainNav().getByRole('link', { name: 'Dashboard' })).toBeInTheDocument();

    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' }, PAGE_LOAD)).toBeInTheDocument();
    expect(screen.queryByText('Loading page…')).not.toBeInTheDocument();
  });

  it('opens the claim named in a /claims/:id deep link', async () => {
    mockApi({ ...HEALTHY, 'GET /claims/clm-1': { data: claim } });
    renderWithRouter(<App />, { route: '/claims/clm-1' });

    expect(screen.getByRole('status')).toHaveTextContent('Loading page…');
    expect(await screen.findByRole('heading', { level: 1, name: 'CLM-2026-00001' }, PAGE_LOAD)).toBeInTheDocument();
  });

  it('shows the 404 page for an unknown address, and navigates from it to a lazy page', async () => {
    mockApi({ ...HEALTHY, 'GET /claims': { data: { claims: [], total: 0 } } });
    const { user } = renderWithRouter(<App />, { route: '/no-such-page' });

    // The 404 page is in the main bundle, so it renders without a placeholder.
    expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();

    await user.click(mainNav().getByRole('link', { name: 'Claims' }));

    expect(await screen.findByRole('heading', { level: 1, name: 'Claims' }, PAGE_LOAD)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Page not found' })).not.toBeInTheDocument();
  });
});
