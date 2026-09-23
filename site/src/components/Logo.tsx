import type { FC } from 'react';

/** Leaf icon used in the header — a minimal sprout/seedling shape so the
 * brand is visible even before the page loads its hero image. */
export const Logo: FC<{ className?: string }> = ({ className }) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <line x1="12" y1="5" x2="12" y2="12" />
    <path d="M12 5a5 5 0 0 0 0 10" />
    <path d="M12 12A5 5 0 0 1 17 12a5 5 0 0 1 0 10" />
  </svg>
);
