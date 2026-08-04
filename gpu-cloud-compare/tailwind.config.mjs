/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./src/**/*.{astro,html,js,jsx,ts,tsx,md,mdx}"],
  theme: {
    extend: {
      colors: {
        // Dark B2B/dev surface scale
        surface: {
          950: "#05070a",
          900: "#0a0e14",
          850: "#0e131b",
          800: "#131a24",
          700: "#1b2430",
          600: "#26313f",
          500: "#374357",
        },
        // Neon accents
        neon: {
          green: "#39ff9c",
          "green-dim": "#1fae6c",
          blue: "#3ab5ff",
          "blue-dim": "#1f7fae",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
      boxShadow: {
        "neon-green": "0 0 0 1px rgba(57,255,156,0.25), 0 0 24px -4px rgba(57,255,156,0.35)",
        "neon-blue": "0 0 0 1px rgba(58,181,255,0.25), 0 0 24px -4px rgba(58,181,255,0.35)",
      },
      backgroundImage: {
        "grid-fade":
          "linear-gradient(to bottom, rgba(57,255,156,0.06), transparent 60%), radial-gradient(circle at top, rgba(58,181,255,0.10), transparent 45%)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
    },
  },
  plugins: [],
};
