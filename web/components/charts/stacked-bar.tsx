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
            stroke="#E5E2DC"
            horizontal={isHorizontal}
            vertical={!isHorizontal}
          />
          <XAxis
            type={isHorizontal ? "category" : "number"}
            dataKey={isHorizontal ? xKey : undefined}
            stroke="#8A8E94"
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
            tick={{ fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}
          />
          <YAxis
            type={isHorizontal ? "number" : "category"}
            dataKey={isHorizontal ? undefined : xKey}
            stroke="#8A8E94"
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
            width={isHorizontal ? 28 : 80}
            tick={{ fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}
          />
          <Tooltip
            cursor={{ fill: "rgba(0,0,0,0.03)" }}
            contentStyle={{
              border: "1px solid #E5E2DC",
              borderRadius: 4,
              background: "#FFFFFF",
              fontSize: 12,
              fontFamily: "JetBrains Mono, monospace",
              color: "#0F1419",
            }}
            labelStyle={{ color: "#8A8E94" }}
            itemStyle={{ color: "#0F1419" }}
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
