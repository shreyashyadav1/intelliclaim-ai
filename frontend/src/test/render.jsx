import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

/**
 * Renders `ui` inside a MemoryRouter at `route`. Pass `path` (e.g. "/claims/:id")
 * when the component reads route params. Returns RTL's result plus a user-event instance.
 */
export function renderWithRouter(ui, { route = '/', path } = {}) {
  const user = userEvent.setup();
  const content = path ? (
    <Routes>
      <Route path={path} element={ui} />
    </Routes>
  ) : ui;
  return { user, ...render(<MemoryRouter initialEntries={[route]}>{content}</MemoryRouter>) };
}
