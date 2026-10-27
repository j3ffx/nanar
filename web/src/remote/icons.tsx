// The remote's icons: 24×24, drawn with the current text colour.

import type { ReactNode, SVGProps } from 'react';

function Icon({ children, ...props }: SVGProps<SVGSVGElement> & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export const Play = () => (
  <Icon>
    <path d="M7 4.5v15l12.5-7.5z" fill="currentColor" />
  </Icon>
);

export const Pause = () => (
  <Icon>
    <rect x="6" y="4.5" width="4" height="15" rx="1" fill="currentColor" />
    <rect x="14" y="4.5" width="4" height="15" rx="1" fill="currentColor" />
  </Icon>
);

export const Previous = () => (
  <Icon>
    <path d="M18 5v14L8 12z" fill="currentColor" />
    <path d="M6 5v14" />
  </Icon>
);

export const Next = () => (
  <Icon>
    <path d="M6 5v14l10-7z" fill="currentColor" />
    <path d="M18 5v14" />
  </Icon>
);

export const Stop = () => (
  <Icon>
    <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />
  </Icon>
);

/** A circular arrow, backwards or forwards, with the number of seconds inside. */
export function Jump({ seconds }: { seconds: number }) {
  const back = seconds < 0;
  const label = Math.abs(seconds) >= 60 ? `${Math.abs(seconds) / 60}′` : String(Math.abs(seconds));
  return (
    <Icon>
      <g transform={back ? undefined : 'translate(24 0) scale(-1 1)'}>
        <path d="M4 12a8 8 0 1 0 2.4-5.7" />
        <path d="M4 3v4.5h4.5" />
      </g>
      <text
        x="12.3"
        y="15.6"
        textAnchor="middle"
        fontSize="8.5"
        fontWeight="700"
        fill="currentColor"
        stroke="none"
      >
        {label}
      </text>
    </Icon>
  );
}

export const Volume = () => (
  <Icon>
    <path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z" fill="currentColor" />
    <path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11" />
  </Icon>
);

export const Muted = () => (
  <Icon>
    <path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z" fill="currentColor" />
    <path d="M16 9.5l5 5M21 9.5l-5 5" />
  </Icon>
);

export const Fullscreen = () => (
  <Icon>
    <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />
  </Icon>
);

export const ExitFullscreen = () => (
  <Icon>
    <path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" />
  </Icon>
);

export const Speech = () => (
  <Icon>
    <path d="M4 5h16v11H9l-5 4z" />
    <path d="M8 9.5h8M8 12.5h5" />
  </Icon>
);

export const Subtitles = () => (
  <Icon>
    <rect x="3" y="5" width="18" height="14" rx="2.5" />
    <path d="M7 14h4M13 14h4M7 10.5h2M11 10.5h6" />
  </Icon>
);

export const Check = () => (
  <Icon>
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  </Icon>
);

export const Grid = () => (
  <Icon>
    <rect x="4" y="4" width="7" height="9" rx="1.5" />
    <rect x="13" y="4" width="7" height="9" rx="1.5" />
    <rect x="4" y="15" width="7" height="5" rx="1.5" />
    <rect x="13" y="15" width="7" height="5" rx="1.5" />
  </Icon>
);
