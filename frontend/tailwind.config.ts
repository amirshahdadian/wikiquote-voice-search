import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#2b3437",
        ember: "#34647d",
        sand: "#f8f9fa",
        fog: "#586064",
        pine: "#275771",
        scholarly: {
          background: "#f8f9fa",
          surface: "#f8f9fa",
          low: "#f1f4f6",
          card: "#ffffff",
          high: "#e3e9ec",
          highest: "#dbe4e7",
          line: "#abb3b7",
          primary: "#34647d",
          primaryDim: "#275771",
          primarySoft: "#c4e7ff",
          secondary: "#e1e2e5",
          tertiary: "#d4e3ff",
          text: "#2b3437",
          muted: "#586064",
          danger: "#9f403d",
          dangerSoft: "#fe8983",
        },
      },
      boxShadow: {
        card: "0 24px 60px rgba(43, 52, 55, 0.06)",
        float: "0 20px 50px rgba(43, 52, 55, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
