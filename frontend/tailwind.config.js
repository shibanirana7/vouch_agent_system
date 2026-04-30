/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"DM Sans"', 'Inter', 'sans-serif'],
      },
      colors: {
        blush: {
          50: '#fff0f7',
          100: '#ffe0ef',
          200: '#ffc2df',
          300: '#ff85bf',
          400: '#ff4da0',
          500: '#ff0066',
          600: '#cc0052',
          700: '#99003d',
        },
        mauve: {
          50: '#fdf2ff',
          100: '#f7e0ff',
          200: '#ecb3ff',
          300: '#dc7aff',
          400: '#c84dff',
          500: '#b020f5',
          600: '#8c00cc',
          700: '#6600a3',
        },
      },
      boxShadow: {
        'pink': '0 4px 24px -4px rgba(255, 0, 102, 0.2)',
        'pink-lg': '0 8px 40px -8px rgba(255, 0, 102, 0.3)',
      },
    },
  },
  plugins: [],
}
