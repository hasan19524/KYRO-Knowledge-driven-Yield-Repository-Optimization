import type { CSSProperties } from "react";

interface KyroLogoProps {
  /** Rendered size in px (square box; artwork keeps its aspect via object-fit). */
  size?: number;
  className?: string;
  alt?: string;
}

/**
 * KYRO mark. One <img> per theme; globals.css hides the inactive one using
 * [data-theme] on <body>. Assets are used exactly as shipped in /public/logo.
 */
export default function KyroLogo({
  size = 64,
  className = "",
  alt = "KYRO",
}: KyroLogoProps) {
  // NOTE: no `display` here on purpose — inline display would override the
  // [data-theme] rule in globals.css that hides the inactive variant, making
  // both logos show at once. display/visibility are owned by CSS only.
  const box: CSSProperties = {
    width: size,
    height: size,
    objectFit: "contain",
    flexShrink: 0,
  };

  return (
    <>
      {/* eslint-disable-next-line @next/next/no-img-element -- local static SVG */}
      <img
        src="/logo/kyro-logo-dark.svg"
        alt={alt}
        width={size}
        height={size}
        draggable={false}
        className={`kyro-logo kyro-logo--dark ${className}`}
        style={box}
      />
      {/* eslint-disable-next-line @next/next/no-img-element -- local static SVG */}
      <img
        src="/logo/kyro-logo-light.svg"
        alt=""
        width={size}
        height={size}
        draggable={false}
        className={`kyro-logo kyro-logo--light ${className}`}
        style={box}
      />
    </>
  );
}
