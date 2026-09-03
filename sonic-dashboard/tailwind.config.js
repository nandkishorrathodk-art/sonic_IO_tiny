/** @type {import('tailwindcss').Config} */
const colors = require("tailwindcss/colors");

module.exports = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // ── Surface scale (deep, layered dark) ──────────────────────
        ink: {
          950: "#070910",
          900: "#0B0E16",
          850: "#0F131C",
          800: "#141823",
          750: "#1A1F2B",
          700: "#222835",
          600: "#2D3444",
          500: "#3A4255",
        },
        // ── Text / muted ────────────────────────────────────────────
        slate: colors.slate,
        muted: {
          DEFAULT: "#8B93A7",
          dim: "#5B6477",
          bright: "#C3CAD8",
        },
        // ── Brand accents (Red Team + Cyber Cyan) ───────────────────
        primary: {
          DEFAULT: "#FF3B5C",
          400: "#FF6B85",
          500: "#FF3B5C",
          600: "#E5264A",
          700: "#B81A38",
        },
        secondary: {
          DEFAULT: "#22D3EE",
          400: "#5AE6F7",
          500: "#22D3EE",
          600: "#06B6D4",
          700: "#0E8FAB",
        },
        accent: {
          DEFAULT: "#8B5CF6",
          400: "#A78BFA",
          500: "#8B5CF6",
          600: "#7C3AED",
        },
        success: "#22E0A1",
        warning: "#FBBF24",
        danger: "#FF5C5C",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        glow: "0 0 24px rgba(255, 59, 92, 0.22)",
        "glow-cyan": "0 0 24px rgba(34, 211, 238, 0.22)",
        "glow-violet": "0 0 24px rgba(139, 92, 246, 0.22)",
        "inner-glow": "inset 0 1px 0 0 rgba(255,255,255,0.04)",
      },
      backgroundImage: {
        "grid-glow":
          "radial-gradient(circle at 20% 0%, rgba(255,59,92,0.10), transparent 40%), radial-gradient(circle at 80% 100%, rgba(34,211,238,0.10), transparent 45%)",
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.8)", opacity: "0.6" },
          "100%": { transform: "scale(2.2)", opacity: "0" },
        },
      },
      animation: {
        shimmer: "shimmer 2s linear infinite",
        "fade-in-up": "fade-in-up 0.4s ease-out both",
        "pulse-ring": "pulse-ring 1s ease-out",
      },
    },
  },
  plugins: [],
};

