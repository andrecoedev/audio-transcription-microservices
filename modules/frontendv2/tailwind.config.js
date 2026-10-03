/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#edf4f0',
          100: '#dce9e1',
          200: '#b8d1c1',
          300: '#90b59f',
          400: '#619378',
          500: '#3d7056',
          600: '#203c34',
          700: '#192f29',
          800: '#14261f',
          900: '#0e1b16',
        },
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}
