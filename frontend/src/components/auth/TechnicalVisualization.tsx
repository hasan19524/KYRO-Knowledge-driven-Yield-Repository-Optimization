import type { ReactNode } from "react";

interface TechnicalVisualizationProps {
  mode: "login" | "signup";
  className?: string;
}

const ISO_C = 0.866;
const SAGE = "#5F795F";
const STROKE_SAGE = "rgba(95, 121, 95, 0.45)";
const STROKE_PLATE = "rgba(234, 231, 220, 0.14)";
const GRID_LINE = "rgba(234, 231, 220, 0.06)";
const CODE_DIM = "rgba(234, 231, 220, 0.3)";

type Point = [number, number, number];

function iso(x: number, y: number, z: number): [number, number] {
  return [
    Math.round((x - y) * ISO_C * 100) / 100,
    Math.round(((x + y) / 2 - z) * 100) / 100,
  ];
}

function poly(points: Point[]): string {
  return points.map((p) => iso(p[0], p[1], p[2]).join(",")).join(" ");
}

function isoTransform(x: number, y: number, z: number): string {
  const [tx, ty] = iso(x, y, z);
  return `matrix(${ISO_C} 0.5 ${-ISO_C} 0.5 ${tx} ${ty})`;
}

function faceTransform(x: number, y: number, z: number): string {
  const [tx, ty] = iso(x, y, z);
  return `matrix(${ISO_C} 0.5 0 1 ${tx} ${ty})`;
}

interface IsoBoxProps {
  x: number;
  y: number;
  z: number;
  w: number;
  d: number;
  h: number;
  top?: string;
  right?: string;
  left?: string;
  stroke?: string;
}

function IsoBox({
  x,
  y,
  z,
  w,
  d,
  h,
  top = "#1A1E18",
  right = "#151813",
  left = "#090A08",
  stroke = STROKE_SAGE,
}: IsoBoxProps) {
  const topFace = poly([
    [x, y, z + h],
    [x + w, y, z + h],
    [x + w, y + d, z + h],
    [x, y + d, z + h],
  ]);
  const rightFace = poly([
    [x + w, y, z + h],
    [x + w, y + d, z + h],
    [x + w, y + d, z],
    [x + w, y, z],
  ]);
  const leftFace = poly([
    [x, y + d, z + h],
    [x + w, y + d, z + h],
    [x + w, y + d, z],
    [x, y + d, z],
  ]);

  return (
    <g stroke={stroke} strokeWidth={1} strokeLinejoin="round">
      <polygon points={leftFace} fill={left} />
      <polygon points={rightFace} fill={right} />
      <polygon points={topFace} fill={top} />
    </g>
  );
}

function GroundGrid() {
  const marks = [10, 50, 90, 130, 170, 210];
  return (
    <g stroke={GRID_LINE} strokeWidth={1}>
      {marks.map((v) => (
        <g key={v}>
          <line
            x1={iso(v, 10, 0)[0]}
            y1={iso(v, 10, 0)[1]}
            x2={iso(v, 210, 0)[0]}
            y2={iso(v, 210, 0)[1]}
          />
          <line
            x1={iso(10, v, 0)[0]}
            y1={iso(10, v, 0)[1]}
            x2={iso(210, v, 0)[0]}
            y2={iso(210, v, 0)[1]}
          />
        </g>
      ))}
    </g>
  );
}

function BasePlate() {
  return (
    <IsoBox
      x={25}
      y={25}
      z={0}
      w={170}
      d={170}
      h={3}
      top="#12150F"
      right="#0F120E"
      left="#090A08"
      stroke={STROKE_PLATE}
    />
  );
}

function StackScene() {
  const bars = [42, 66, 54, 88];
  return (
    <g>
      <GroundGrid />
      <BasePlate />
      {bars.map((h, i) => {
        const accent = i === bars.length - 1;
        return (
          <IsoBox
            key={`bar-${i}`}
            x={148 + i * 12}
            y={30}
            z={3}
            w={10}
            d={36}
            h={h}
            top={accent ? "#304D3A" : "#1A1E18"}
            right={accent ? "#1A1E18" : "#151813"}
            left={accent ? "#090A08" : "#0F120E"}
          />
        );
      })}
      <IsoBox x={30} y={60} z={3} w={110} d={110} h={10} />
      <IsoBox x={42} y={72} z={15} w={86} d={86} h={10} />
      <IsoBox x={54} y={84} z={27} w={62} d={62} h={10} />
      <g transform={isoTransform(85, 115, 37)}>
        <image
          href="/logo/kyro-logo-dark.svg"
          x={-24}
          y={-24}
          width={48}
          height={48}
          preserveAspectRatio="xMidYMid meet"
        />
      </g>
    </g>
  );
}

const CODE_LINES: { u: number; v: number; w: number; fill: string }[] = [
  { u: 6, v: 16, w: 74, fill: CODE_DIM },
  { u: 16, v: 29, w: 48, fill: SAGE },
  { u: 16, v: 42, w: 92, fill: "rgba(234, 231, 220, 0.18)" },
  { u: 28, v: 55, w: 56, fill: CODE_DIM },
  { u: 16, v: 68, w: 38, fill: "rgba(95, 121, 95, 0.85)" },
  { u: 6, v: 81, w: 64, fill: "rgba(234, 231, 220, 0.16)" },
];

function WallScene() {
  return (
    <g>
      <GroundGrid />
      <BasePlate />
      <IsoBox x={45} y={35} z={3} w={140} d={6} h={95} />
      <g transform={faceTransform(45, 41, 98)}>
        <circle cx={8} cy={7} r={2} fill="rgba(234, 231, 220, 0.32)" />
        <circle cx={17} cy={7} r={2} fill="rgba(234, 231, 220, 0.22)" />
        <circle cx={26} cy={7} r={2} fill="rgba(234, 231, 220, 0.14)" />
        {CODE_LINES.map((line) => (
          <rect
            key={`${line.u}-${line.v}`}
            x={line.u}
            y={line.v}
            width={line.w}
            height={5}
            rx={2.5}
            fill={line.fill}
          />
        ))}
      </g>
      <g transform={isoTransform(45, 55, 4)}>
        <line
          x1={0}
          y1={50}
          x2={140}
          y2={50}
          stroke="rgba(234, 231, 220, 0.16)"
          strokeWidth={1}
          strokeDasharray="4 5"
        />
        <polyline
          points="2,44 24,38 46,41 68,28 90,31 112,15 132,8"
          fill="none"
          stroke={SAGE}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx={132} cy={8} r={3.5} fill={SAGE} />
      </g>
      <IsoBox x={70} y={110} z={3} w={70} d={70} h={6} />
      <g transform={isoTransform(105, 145, 9)}>
        <image
          href="/logo/kyro-logo-dark.svg"
          x={-22}
          y={-22}
          width={44}
          height={44}
          preserveAspectRatio="xMidYMid meet"
        />
      </g>
    </g>
  );
}

function Chip({ className, children }: { className: string; children: ReactNode }) {
  return (
    <span
      className={`absolute hidden items-center gap-1.5 whitespace-nowrap rounded-md border border-[rgba(234,231,220,0.14)] bg-[rgba(9,10,8,0.78)] px-2.5 py-1.5 font-mono text-[10px] uppercase leading-none tracking-[0.1em] text-[#9A9E95] md:inline-flex ${className}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-[#5F795F]" aria-hidden="true" />
      {children}
    </span>
  );
}

export default function TechnicalVisualization({
  mode,
  className = "",
}: TechnicalVisualizationProps) {
  const isLogin = mode === "login";

  return (
    <div className={`relative w-full ${className}`}>
      <svg
        viewBox={isLogin ? "-185 -25 370 255" : "-185 -75 370 305"}
        className="block w-full"
        aria-hidden="true"
        focusable="false"
      >
        {isLogin ? <StackScene /> : <WallScene />}
      </svg>

      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        {isLogin ? (
          <>
            <Chip className="left-0 top-[12%]">repo · 12 indexed</Chip>
            <Chip className="right-[2%] top-[34%]">yield · +38%</Chip>
            <Chip className="bottom-[8%] left-[6%]">sync · 2m ago</Chip>
          </>
        ) : (
          <>
            <Chip className="right-[4%] top-[14%]">workspace · ready</Chip>
            <Chip className="left-0 top-[44%]">schema · validated</Chip>
            <Chip className="bottom-[6%] right-[8%]">build · passing</Chip>
          </>
        )}
      </div>
    </div>
  );
}
