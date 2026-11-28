/** The product mark: a page with one highlighted line, the thing the app is about. */
export default function LogoMark({ size = 24 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="7" fill="var(--ink)" />
      <rect x="8" y="8" width="16" height="3" rx="1.5" fill="var(--sheet)" />
      <rect x="6" y="13.5" width="20" height="6" rx="1.5" fill="var(--mark-strong)" />
      <rect x="8" y="15" width="12" height="3" rx="1.5" fill="var(--ink)" />
      <rect x="8" y="22" width="11" height="3" rx="1.5" fill="var(--sheet)" />
    </svg>
  );
}
