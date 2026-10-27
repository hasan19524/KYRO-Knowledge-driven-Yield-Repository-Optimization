/**
 * KYRO design tokens — source of truth: refrence/
 * Colors mirror the CSS variables defined in src/app/globals.css.
 */
export const design = {
  colors: {
    // Dark mode (default)
    appBackground: "#090A08",
    sidebarBackground: "#0F120E",
    surface: "#151813",
    surfaceHover: "#1A1E18",
    surfaceActive: "#1F241D",
    border: "#292E28",
    borderHover: "rgba(234,231,220,0.16)",
    borderFocus: "#5F795F",
    borderSubtle: "rgba(234,231,220,0.07)",
    textPrimary: "#EAE7DC",
    textSecondary: "rgba(234,231,220,0.72)",
    textMuted: "#9A9E95",
    textSubtle: "rgba(234,231,220,0.42)",
    textInverse: "#090A08",
    accent: "#304D3A",
    accentHover: "#5F795F",
    accentSoft: "rgba(48,77,58,0.24)",
    sageSoft: "rgba(95,121,95,0.20)",
    success: "#5F795F",
    warning: "#9A8B5E",
    error: "#9E5F52",
    overlay: "rgba(9,10,8,0.72)",

    // Light mode
    light: {
      appBackground: "#F3F1E9",
      sidebarBackground: "#E9E7DE",
      surface: "#FFFFFF",
      surfaceHover: "#FBFAF6",
      surfaceActive: "#F1EFE6",
      border: "#D9D9D0",
      textPrimary: "#181815",
      textSecondary: "#3A3D38",
      textMuted: "#686D65",
      overlay: "rgba(24,24,21,0.40)",
    },
  },

  layout: {
    sidebarWidth: "264px",
    sidebarCollapsedWidth: "64px",
    topbarHeight: "56px",
    mainMaxWidth: "900px",
    composerMaxWidth: "900px",
  },

  radius: {
    sm: "6px",
    md: "8px",
    lg: "10px",
    xl: "12px",
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
    none: "none",
    card: "0 1px 2px rgba(0,0,0,0.18)",
    popover: "0 8px 24px rgba(0,0,0,0.35)",
    focus: "0 0 0 2px var(--kyro-accent-soft)",
  },

  fonts: {
    sans: "var(--font-inter), system-ui, -apple-system, sans-serif",
    mono: "var(--font-geist-mono), ui-monospace, monospace",
  },

  fontSize: {
    xs: "11px",
    sm: "12px",
    md: "13px",
    body: "14px",
    lg: "15px",
    h4: "17px",
    h3: "19px",
    h2: "22px",
    h1: "28px",
  },

  transitions: {
    fast: "140ms ease-out",
    normal: "180ms ease-out",
    slow: "300ms ease-out",
  },

  zIndex: {
    topbar: "30",
    overlay: "40",
    sidebar: "50",
  },
} as const;

export type Design = typeof design;
