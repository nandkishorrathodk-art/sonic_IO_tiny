/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#090A0F",
        surface: "#11141E",
        "surface-border": "#1E2436",
        primary: "#EF4444",
        secondary: "#06B6D4",
        accent: "#8B5CF6",
      },
    },
  },
  plugins: [],
};
