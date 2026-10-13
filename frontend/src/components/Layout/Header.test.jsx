import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import Header from './Header';

function CurrentLocation() {
  const location = useLocation();
  return <output aria-label="Current location">{`${location.pathname}${location.search}`}</output>;
}

describe('Header', () => {
  it('opens the claims search for the submitted term', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/']}>
        <Header />
        <CurrentLocation />
      </MemoryRouter>,
    );

    await user.type(screen.getByRole('searchbox', { name: 'Search claims' }), 'knee surgery{Enter}');

    expect(screen.getByLabelText('Current location')).toHaveTextContent('/claims?search=knee+surgery');
    expect(screen.getByRole('searchbox', { name: 'Search claims' })).toHaveValue('');
  });

  it('does not render placeholder profile or notification controls', () => {
    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>,
    );

    expect(screen.queryByRole('button', { name: 'Notifications' })).not.toBeInTheDocument();
    expect(screen.queryByText('SY')).not.toBeInTheDocument();
  });
});
