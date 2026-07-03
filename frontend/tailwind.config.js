/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#12151b",
        panel: "#181c24",
        line: "#262b35",
        accent: "#5eead4",
        warn: "#f5a35c",
        danger: "#f27878",
      },
    },
  },
  plugins: [],
};
