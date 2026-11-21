/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: '#FAFAF9',
        main: '#18181B',
        muted: '#52525B',
        border: '#E4E4E7',
        accent: {
          DEFAULT: '#4338CA',
          hover: '#3730A3',
          tint: '#EEF2FF',
          border: '#C7D2FE',
        }
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        btn: '10px',
        card: '12px',
        chip: '16px',
      }
    },
  },
  plugins: [],
}
