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
        // Editorial light palette: white-first, restrained accents — the
        // original McKinsey-ish look we kept after the dark experiment.
        ink:        "#0A0A0A",
        graphite:   "#1F1F1F",
        slate:      "#4A4A4A",
        muted:      "#6B6B6B",
        dim:        "#8C8C8C",
        rule:       "#E8E5DE",
        rule2:      "#D4D0C8",
        surface:    "#FAFAF7",
        paper:      "#FFFFFF",
        accent:     "#1F4287",
        accentSoft: "#DCE6F2",
        critical:   "#B91C1C",
        warning:    "#A16207",
        success:    "#15803D",
      },
      fontFamily: {
        serif: ['"Source Serif 4"', "Georgia", "serif"],
        sans: ['"Inter"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      fontSize: {
        // Editorial scale.
        eyebrow: ["11px", { lineHeight: "16px", letterSpacing: "0.14em" }],
        meta:    ["12px", { lineHeight: "18px", letterSpacing: "0.02em" }],
        body:    ["15px", { lineHeight: "24px" }],
        lead:    ["17px", { lineHeight: "28px" }],
        h3:      ["20px", { lineHeight: "28px" }],
        h2:      ["28px", { lineHeight: "36px", letterSpacing: "-0.01em" }],
        h1:      ["44px", { lineHeight: "52px", letterSpacing: "-0.02em" }],
        hero:    ["64px", { lineHeight: "72px", letterSpacing: "-0.03em" }],
        figure:  ["40px", { lineHeight: "44px", letterSpacing: "-0.01em" }],
      },
      borderRadius: {
        sm: "2px",
        DEFAULT: "4px",
        md: "6px",
        lg: "10px",
      },
      boxShadow: {
        rule: "0 1px 0 0 #E8E5DE",
      },
    },
  },
  plugins: [],
};

export default config;
