/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        critical: { DEFAULT: '#dc2626', light: '#fef2f2', border: '#fca5a5' },
        high:     { DEFAULT: '#ea580c', light: '#fff7ed', border: '#fdba74' },
        medium:   { DEFAULT: '#ca8a04', light: '#fefce8', border: '#fde047' },
        low:      { DEFAULT: '#2563eb', light: '#eff6ff', border: '#93c5fd' },
      },
    },
  },
  plugins: [],
}
