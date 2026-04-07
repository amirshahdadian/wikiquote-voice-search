import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        surface: {
          bg: "#07080f",
          "card": "rgba(255,255,255,0.06)",
          elevated: "rgba(255,255,255,0.09)",
          border: "rgba(255,255,255,0.08)",
        },
        violet: {
          50: "#f5f3ff",
          100: "#ede9fe",
          200: "#ddd6fe",
          300: "#c4b5fd",
          400: "#a78bfa",
          500: "#8b5cf6",
          600: "#7c3aed",
          700: "#6d28d9",
          800: "#5b21b6",
          900: "#4c1d95",
          950: "#2e1065",
        },
        amber: {
          50: "#fffbeb",
          100: "#fef3c7",
          200: "#fde68a",
          300: "#fcd34d",
          400: "#fbbf24",
          500: "#f59e0b",
          600: "#d97706",
          700: "#b45309",
          800: "#92400e",
          900: "#78350f",
        },
      },
      fontFamily: {
        sans: ["var(--font-geist)", "system-ui", "sans-serif"],
        serif: ["var(--font-lora)", "Georgia", "serif"],
        mono: ["var(--font-geist-mono)", "monospace"],
      },
      backgroundImage: {
        "radial-violet":
          "radial-gradient(ellipse 80% 50% at 20% -10%, rgba(139,92,246,0.18) 0%, transparent 60%)",
        "radial-teal":
          "radial-gradient(ellipse 70% 50% at 80% 110%, rgba(20,184,166,0.12) 0%, transparent 60%)",
        "gradient-violet-amber":
          "linear-gradient(135deg, #8b5cf6 0%, #f59e0b 100%)",
        "gradient-card":
          "linear-gradient(135deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.02) 100%)",
      },
      boxShadow: {
        glow: "0 0 40px rgba(139,92,246,0.25), 0 0 80px rgba(139,92,246,0.08)",
        "glow-sm": "0 0 20px rgba(139,92,246,0.2)",
        "glow-amber": "0 0 30px rgba(245,158,11,0.2)",
        glass: "0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.1)",
        "glass-lg":
          "0 16px 64px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.08)",
        card: "0 4px 24px rgba(0,0,0,0.3)",
        "inner-border": "inset 0 0 0 1px rgba(255,255,255,0.06)",
      },
      backdropBlur: {
        xs: "4px",
        xl: "24px",
        "2xl": "40px",
      },
      animation: {
        "pulse-ring": "pulse-ring 2s cubic-bezier(0.4,0,0.6,1) infinite",
        "pulse-ring-delay": "pulse-ring 2s cubic-bezier(0.4,0,0.6,1) 0.5s infinite",
        "gradient-shift": "gradient-shift 4s ease infinite",
        "bar-bounce": "bar-bounce 1s ease-in-out infinite",
        "fade-up": "fade-up 0.4s ease forwards",
        "spin-slow": "spin 3s linear infinite",
      },
      keyframes: {
        "pulse-ring": {
          "0%": { transform: "scale(1)", opacity: "0.8" },
          "100%": { transform: "scale(2.2)", opacity: "0" },
        },
        "gradient-shift": {
          "0%, 100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
        "bar-bounce": {
          "0%, 100%": { transform: "scaleY(0.4)", opacity: "0.5" },
          "50%": { transform: "scaleY(1)", opacity: "1" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      transitionDuration: {
        "250": "250ms",
        "350": "350ms",
        "400": "400ms",
      },
    },
  },
  plugins: [],
};

export default config;
