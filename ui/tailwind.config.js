/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ['"Plus Jakarta Sans Variable"', "system-ui", "sans-serif"] },
      colors: {
        canvas: "#EAE8E1",
        sage: { 50: "#EEF2EE", 100: "#DDE6DE", 300: "#A9BCAC", 500: "#5C7862", 600: "#4F6A55", 700: "#3F5644" },
        slate: { ink: "#1E2923" },
      },
      borderRadius: { bento: "28px" },
      boxShadow: { card: "0 1px 2px rgba(30,41,35,.04), 0 4px 16px rgba(30,41,35,.04)" },
    },
  },
  plugins: [],
};
