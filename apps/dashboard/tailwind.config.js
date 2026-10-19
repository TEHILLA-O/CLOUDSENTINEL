/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#10151c",
        panel: "#171e28",
        line: "#2c3848",
        ink: "#e8eef7",
        muted: "#93a0b5",
        good: "#3ecf8e",
        warn: "#e6b450",
        bad: "#ef6b73",
        info: "#7eb6ff",
      },
      fontFamily: {
        sans: ["Segoe UI", "system-ui", "sans-serif"],
        mono: ["Cascadia Code", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
