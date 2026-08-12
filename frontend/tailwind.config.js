/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        serif: ["Fraunces", "Georgia", "Cambria", "serif"],
      },
      colors: {
        paper: "#faf8f3",
        surface: "#ffffff",
        ink: {
          DEFAULT: "#1c1b18",
          soft: "#57534b",
          faint: "#8a857a",
        },
        line: {
          DEFAULT: "#e6e2d8",
          strong: "#d7d2c5",
        },
        accent: {
          DEFAULT: "#9a3412",
          soft: "#f3e9e2",
          ink: "#7a2910",
        },
        approve: "#3f6b4f",
        downgrade: "#9a6b2f",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.5s ease-out both",
      },
    },
  },
  plugins: [],
};
