"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface SeriesDef {
  key: string;
  label: string;
  color: string;
}

interface ConflictsAreaChartProps {
  data: Array<Record<string, number | string>>;
  series: SeriesDef[];
  height?: number;
  /** Stack series on top of each other (defaults to true). */
  stacked?: boolean;
  xKey?: string;
}

export function StackedAreaChart({
  data,
  series,
  height = 240,
  stacked = true,
  xKey = "date",
}: ConflictsAreaChartProps) {
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
          <defs>
            {series.map((s) => (
              <linearGradient key={s.key} id={`grad-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity={0.35} />
                <stop offset="100%" stopColor={s.color} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E2DC" vertical={false} />
          <XAxis
            dataKey={xKey}
            stroke="#8A8E94"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}
            tickFormatter={(v) => {
              if (typeof v !== "string") return String(v);
              // "2026-04-26" → "Apr 26"
              const [, m, d] = v.split("-");
              const months = [
                "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
              ];
              return `${months[Number(m) - 1] || m} ${Number(d)}`;
            }}
          />
          <YAxis
            stroke="#8A8E94"
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
            width={28}
            tick={{ fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}
          />
          <Tooltip
            cursor={{ stroke: "#D2CFC9", strokeDasharray: "3 3" }}
            contentStyle={{
              border: "1px solid #E5E2DC",
              borderRadius: 4,
              background: "#FFFFFF",
              fontSize: 12,
              fontFamily: "JetBrains Mono, monospace",
              color: "#0F1419",
            }}
            labelStyle={{ color: "#8A8E94", marginBottom: 4 }}
            itemStyle={{ color: "#0F1419" }}
          />
          {series.map((s) => (
            <Area
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stackId={stacked ? "stack" : undefined}
              stroke={s.color}
              strokeWidth={1.5}
              fill={`url(#grad-${s.key})`}
              isAnimationActive={false}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
