/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts}"],
  theme: {
    extend: {
      colors: {
        primary: "#1D4ED8", // Blue for buttons and accents
        secondary: "#F3F4F6", // Light gray for backgrounds
        accent: "#10B981", // Green for success states
      },
    },
  },
  plugins: [],
};
