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
        // Engineering-tool palette: warm off-white surface, Linear purple
        // accent, slightly muted status colors. Inspired by Linear, Vercel,
        // Anthropic.com — no Tailwind-default indigo here.
        ink:        "#1A1A1A",
        graphite:   "#26262A",
        slate:      "#4A4A4F",
        muted:      "#6F6F73",
        dim:        "#A0A0A4",
        rule:       "#EAE6DD",  // warm hairline
        rule2:      "#D9D3C5",
        surface:    "#FAF8F4",  // warm off-white
        paper:      "#FFFFFF",
        accent:     "#5E6AD2",  // Linear purple
        accentSoft: "#EEEFF9",
        critical:   "#C13832",  // muted red
        warning:    "#B26800",  // muted amber
        success:    "#2A8A52",  // muted emerald
      },
      fontFamily: {
        sans: ['"Inter"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
        // Legacy alias — points at sans so any leftover `font-serif` class
        // doesn't fall back to a system serif.
        serif: ['"Inter"', "system-ui", "sans-serif"],
      },
      fontSize: {
        eyebrow: ["10.5px", { lineHeight: "14px", letterSpacing: "0.06em" }],
        meta:    ["12.5px", { lineHeight: "18px" }],
        body:    ["14px", { lineHeight: "22px" }],
        lead:    ["15.5px", { lineHeight: "24px" }],
        h3:      ["16px", { lineHeight: "22px", letterSpacing: "-0.005em" }],
        h2:      ["20px", { lineHeight: "28px", letterSpacing: "-0.012em" }],
        h1:      ["26px", { lineHeight: "32px", letterSpacing: "-0.018em" }],
        figure:  ["28px", { lineHeight: "32px", letterSpacing: "-0.01em" }],
        hero:    ["38px", { lineHeight: "44px", letterSpacing: "-0.02em" }],
      },
      borderRadius: {
        none: "0",
        sm: "2px",
        DEFAULT: "4px",
        md: "5px",
        lg: "6px",
      },
      boxShadow: {
        rule: "0 1px 0 0 #EAE6DD",
        // Used sparingly — hover/focus only. Default cards are flat with borders.
        focus: "0 0 0 3px rgba(94, 106, 210, 0.18)",
      },
    },
  },
  plugins: [],
};

export default config;
