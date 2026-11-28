import { Outlet } from 'react-router-dom';
import Header from './Header';
import DemoDataNote from '../Shared/DemoDataNote';
import OfflineBanner from '../Shared/OfflineBanner';
import './Layout.css';

export default function Layout() {
  return (
    <div className="layout-root">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <DemoDataNote />
      <Header />
      <OfflineBanner />
      <main className="layout-main" id="main-content" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
