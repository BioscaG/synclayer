"use client";

import {
  Bar,
  BarChart,
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

interface StackedBarProps {
  data: Array<Record<string, number | string>>;
  series: SeriesDef[];
  xKey?: string;
  height?: number;
  layout?: "horizontal" | "vertical";
}

export function StackedBar({
  data,
  series,
  xKey = "name",
  height = 240,
  layout = "horizontal",
}: StackedBarProps) {
  const isHorizontal = layout === "horizontal";
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout={layout}
          margin={{ top: 8, right: 12, left: layout === "vertical" ? 0 : -12, bottom: 0 }}
          barCategoryGap={layout === "vertical" ? "20%" : "30%"}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="#E8E5DE"
            horizontal={isHorizontal}
            vertical={!isHorizontal}
          />
          <XAxis
            type={isHorizontal ? "category" : "number"}
            dataKey={isHorizontal ? xKey : undefined}
            stroke="#8C8C8C"
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
            tick={{ fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}
          />
          <YAxis
            type={isHorizontal ? "number" : "category"}
            dataKey={isHorizontal ? undefined : xKey}
            stroke="#8C8C8C"
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
            width={isHorizontal ? 28 : 80}
            tick={{ fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}
          />
          <Tooltip
            cursor={{ fill: "rgba(0,0,0,0.03)" }}
            contentStyle={{
              border: "1px solid #E8E5DE",
              borderRadius: 4,
              background: "#FFFFFF",
              fontSize: 12,
              fontFamily: "JetBrains Mono, monospace",
              color: "#0A0A0A",
            }}
            labelStyle={{ color: "#6B6B6B" }}
            itemStyle={{ color: "#0A0A0A" }}
          />
          {series.map((s, i) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.label}
              stackId="stack"
              fill={s.color}
              radius={
                i === series.length - 1
                  ? isHorizontal
                    ? [3, 3, 0, 0]
                    : [0, 3, 3, 0]
                  : 0
              }
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
