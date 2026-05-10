/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#eef7ff',
          100: '#d9ecff',
          200: '#bbdeff',
          300: '#8bc9ff',
          400: '#52aafa',
          500: '#2a8af6',
          600: '#1a6eeb',
          700: '#1358d8',
          800: '#1548ae',
          900: '#173e89',
          950: '#122754',
        }
      }
    }
  },
  plugins: []
}
