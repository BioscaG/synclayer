"use client";

import { Area, AreaChart, ResponsiveContainer } from "recharts";

interface SparklineProps {
  data: number[];
  /** "default" | "critical" | "warning" | "success" | "accent" */
  tone?: "default" | "critical" | "warning" | "success" | "accent";
  height?: number;
}

const TONE_STROKE: Record<string, string> = {
  default: "#5A6068",
  accent: "#1E3A8A",
  critical: "#B91C1C",
  warning: "#B45309",
  success: "#15803D",
};

export function Sparkline({
  data,
  tone = "default",
  height = 36,
}: SparklineProps) {
  // Recharts wants {value} objects.
  const series = data.map((v, i) => ({ x: i, value: v }));
  const stroke = TONE_STROKE[tone];
  const id = `spark-${tone}-${data.length}`;

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={series} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.18} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="value"
            stroke={stroke}
            strokeWidth={1.5}
            fill={`url(#${id})`}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
