/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        brand: {
          DEFAULT: "#14B8A6",
          light: "#5EEAD4",
          dark: "#0D9488",
        },
        ink: {
          950: "#071A2B",
          900: "#0B2538",
          800: "#0D2F43",
          700: "#102F43",
          600: "#153F52",
        },
      },
      boxShadow: {
        glow: "0 0 40px -8px rgba(20, 184, 166, 0.35)",
        "glow-strong": "0 0 60px -10px rgba(6, 182, 212, 0.45)",
        "glow-cyan": "0 0 45px -12px rgba(34, 211, 238, 0.45)",
        "glow-teal": "0 0 45px -12px rgba(20, 184, 166, 0.45)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(14px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "message-in": {
          "0%": { opacity: "0", transform: "translateY(8px) scale(0.98)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        "follow-up-in": {
          "0%": { opacity: "0", transform: "scale(0.85)" },
          "60%": { opacity: "1", transform: "scale(1.06)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        blink: {
          "0%, 80%, 100%": { opacity: "0.25" },
          "40%": { opacity: "1" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-12px)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.6s cubic-bezier(0.22, 1, 0.36, 1) both",
        "message-in": "message-in 0.35s cubic-bezier(0.22, 1, 0.36, 1) both",
        "follow-up-in": "follow-up-in 0.5s ease-out both",
        blink: "blink 1.2s infinite",
        float: "float 8s ease-in-out infinite",
        shimmer: "shimmer 1.8s linear infinite",
      },
    },
  },
  plugins: [],
};
