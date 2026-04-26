"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

interface Slice {
  name: string;
  value: number;
  color: string;
}

interface DonutChartProps {
  data: Slice[];
  height?: number;
  centerLabel?: string;
  centerValue?: string | number;
}

export function DonutChart({
  data,
  height = 240,
  centerLabel,
  centerValue,
}: DonutChartProps) {
  const total = data.reduce((acc, d) => acc + d.value, 0);
  const empty = total === 0;

  return (
    <div className="relative" style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={empty ? [{ name: "—", value: 1, color: "#E8E5DE" }] : data}
            dataKey="value"
            innerRadius="62%"
            outerRadius="92%"
            paddingAngle={empty ? 0 : 2}
            stroke="none"
            isAnimationActive={false}
          >
            {(empty ? [{ color: "#E8E5DE" }] : data).map((d, i) => (
              <Cell key={i} fill={d.color} />
            ))}
          </Pie>
          {!empty && (
            <Tooltip
              contentStyle={{
                border: "1px solid #E8E5DE",
                borderRadius: 4,
                background: "#FFFFFF",
                fontSize: 12,
                fontFamily: "JetBrains Mono, monospace",
                color: "#0A0A0A",
              }}
              itemStyle={{ color: "#0A0A0A" }}
            />
          )}
        </PieChart>
      </ResponsiveContainer>

      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <div className="font-mono tabular-nums font-medium text-figure leading-none text-ink">
          {centerValue ?? total}
        </div>
        {centerLabel && (
          <div className="eyebrow mt-2">{centerLabel}</div>
        )}
      </div>
    </div>
  );
}
