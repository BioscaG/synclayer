import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: { DEFAULT: "1.5rem", lg: "2.5rem" },
      screens: { "2xl": "1280px" },
    },
    extend: {
      colors: {
        // The Operator palette — warm cream surface, near-black ink with a
        // subtle cool tint, cobalt as the lone accent for highlights.
        // Status colors at the 700 tier so they read as serious, not neon.
        ink:        "#0F1419",  // primary text + primary CTA bg
        graphite:   "#2D3339",  // emphasis text
        slate:      "#5A6068",  // body secondary
        muted:      "#8A8E94",  // labels
        dim:        "#B5B8BD",  // placeholders / disabled
        rule:       "#E5E2DC",  // warm hairlines
        rule2:      "#D2CFC9",  // input borders / stronger
        surface:    "#F8F7F4",  // page bg, warm cream
        paper:      "#FFFFFF",  // card bg
        accent:     "#1E3A8A",  // deep cobalt — links, active, highlights only
        accentSoft: "#DBE4F5",  // light cobalt for soft backgrounds
        critical:   "#B91C1C",  // red-700, deeper than red-600
        warning:    "#B45309",  // amber-700
        success:    "#15803D",  // emerald-700
      },
      fontFamily: {
        sans: ['"Inter"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
        // Legacy alias — points at sans so old class refs don't fall back.
        serif: ['"Inter"', "system-ui", "sans-serif"],
      },
      fontSize: {
        // Tighter at the small end, more dramatic at the top so KPIs and
        // page headlines have real presence on the page.
        eyebrow: ["10.5px", { lineHeight: "14px", letterSpacing: "0.08em" }],
        meta:    ["12px",   { lineHeight: "18px" }],
        body:    ["13.5px", { lineHeight: "20px" }],
        lead:    ["15px",   { lineHeight: "22px" }],
        h3:      ["17px",   { lineHeight: "24px", letterSpacing: "-0.005em" }],
        h2:      ["22px",   { lineHeight: "28px", letterSpacing: "-0.015em" }],
        h1:      ["30px",   { lineHeight: "36px", letterSpacing: "-0.02em" }],
        figure:  ["36px",   { lineHeight: "40px", letterSpacing: "-0.02em" }],
        hero:    ["56px",   { lineHeight: "60px", letterSpacing: "-0.025em" }],
      },
      borderRadius: {
        none: "0",
        sm: "3px",
        DEFAULT: "5px",
        md: "6px",
        lg: "8px",
      },
      boxShadow: {
        rule: "0 1px 0 0 #E5E2DC",
        focus: "0 0 0 3px rgba(30, 58, 138, 0.15)",
      },
    },
  },
  plugins: [],
};

export default config;
