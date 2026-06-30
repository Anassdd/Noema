// Inline stroke icons in the Noema theme style (stroke = currentColor, so color
// is set by the parent's text color / CSS var). One small helper, one icon per
// export — keeps every icon consistent in weight and size.
export function Icon({ size = 16, sw = 1.7, children, ...rest }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={sw}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const NewChatIcon = (p) => (
  <Icon {...p}>
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
  </Icon>
);

export const PanelIcon = (p) => (
  <Icon {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2.5" />
    <path d="M9 4v16" />
  </Icon>
);

export const BrainIcon = (p) => (
  <Icon {...p}>
    <path d="M12 5a3 3 0 0 0-3 3 2.5 2.5 0 0 0-2 4 2.5 2.5 0 0 0 1.2 4.4A2.5 2.5 0 0 0 12 19a2.5 2.5 0 0 0 3.8-2.6A2.5 2.5 0 0 0 17 12a2.5 2.5 0 0 0-2-4 3 3 0 0 0-3-3z" />
    <path d="M12 5v14" />
  </Icon>
);

export const FileIcon = (p) => (
  <Icon size={15} {...p}>
    <path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8l-5-5z" />
    <path d="M14 3v5h5" />
  </Icon>
);

export const SunIcon = (p) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </Icon>
);

export const MoonIcon = (p) => (
  <Icon {...p}>
    <path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z" />
  </Icon>
);

export const PlusIcon = (p) => (
  <Icon {...p}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
);

export const SendIcon = (p) => (
  <Icon {...p}>
    <path d="M12 19V5M6 11l6-6 6 6" />
  </Icon>
);

export const StopIcon = (p) => (
  <Icon {...p} fill="currentColor" stroke="none">
    <rect x="6" y="6" width="12" height="12" rx="2.5" />
  </Icon>
);

export const TrashIcon = (p) => (
  <Icon {...p}>
    <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
    <path d="M10 11v6M14 11v6" />
  </Icon>
);

export const GearIcon = (p) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </Icon>
);

export const ChevronDownIcon = (p) => (
  <Icon {...p}>
    <path d="M6 9l6 6 6-6" />
  </Icon>
);

export const CheckIcon = (p) => (
  <Icon {...p}>
    <path d="M20 6L9 17l-5-5" />
  </Icon>
);

export const SparkIcon = (p) => (
  <Icon {...p} fill="currentColor" stroke="none">
    <path d="M13 2L3 14h7l-1 8 10-12h-7l1-8z" />
  </Icon>
);

export const CloseIcon = (p) => (
  <Icon {...p}>
    <path d="M18 6L6 18M6 6l12 12" />
  </Icon>
);

export const GraphIcon = (p) => (
  <Icon {...p}>
    <circle cx="5" cy="6" r="2.2" />
    <circle cx="18" cy="6" r="2.2" />
    <circle cx="12" cy="18" r="2.2" />
    <path d="M6.8 7.2L11 16.4M16.2 7.2L13 16.4M7 6h8.5" />
  </Icon>
);
