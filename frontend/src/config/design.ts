export const design = {
  colors: {
    appBackground: "#08090b",
    sidebarBackground: "#0b0d12",
    surface: "#12151c",
    surfaceHover: "#1a1e27",
    surfaceActive: "#22262f",
    border: "rgba(255,255,255,0.08)",
    borderHover: "rgba(255,255,255,0.12)",
    borderFocus: "rgba(255,255,255,0.16)",
    borderSubtle: "rgba(255,255,255,0.06)",
    textPrimary: "#f5f5f5",
    textSecondary: "#8f96a3",
    textMuted: "#626977",
    textSubtle: "#4a5060",
    textMind: "#9ca3af",
    accent: "#c8cdd6",
    accentHover: "#f5f5f5",
    success: "#22c55e",
    warning: "#eab308",
    error: "#ef4444",
  },

  layout: {
    sidebarWidth: "310px",
    sidebarCollapsedWidth: "60px",
    mainMaxWidth: "900px",
    composerMaxWidth: "900px",
  },

  radius: {
    sm: "6px",
    md: "8px",
    lg: "12px",
    xl: "14px",
    "2xl": "18px",
    full: "9999px",
  },

  spacing: {
    xs: "4px",
    sm: "8px",
    md: "12px",
    lg: "16px",
    xl: "24px",
    "2xl": "32px",
    "3xl": "48px",
    "4xl": "64px",
  },

  shadows: {
    card: "0 1px 2px rgba(0,0,0,0.3), 0 1px 3px rgba(0,0,0,0.15)",
    input: "0 1px 2px rgba(0,0,0,0.2)",
    hover: "0 4px 12px rgba(0,0,0,0.25)",
    focus: "0 0 0 2px rgba(255,255,255,0.08)",
  },

  fonts: {
    sans: "var(--font-geist-sans), system-ui, -apple-system, sans-serif",
    mono: "var(--font-geist-mono), ui-monospace, monospace",
  },

  fontSize: {
    xs: "11px",
    sm: "13px",
    md: "15px",
    lg: "17px",
    xl: "24px",
    "2xl": "32px",
    "3xl": "40px",
  },

  transitions: {
    fast: "120ms ease",
    normal: "200ms ease",
    slow: "300ms ease",
  },

  zIndex: {
    sidebar: "40",
    overlay: "50",
    topbar: "30",
  },
} as const;

export type Design = typeof design;
