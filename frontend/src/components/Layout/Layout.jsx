import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Header from './Header';

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />
      <div style={{ flex: 1, marginLeft: 260, minWidth: 0 }}>
        <Header />
        <main
          style={{ padding: '24px 32px', maxWidth: 1400, margin: '0 auto' }}
          role="main"
        >
          <Outlet />
        </main>
      </div>
      <style>{`
        @media (max-width: 768px) {
          div[style*="marginLeft: 260"] {
            margin-left: 0 !important;
          }
          main[style] {
            padding: 16px !important;
          }
        }
      `}</style>
    </div>
  );
}
