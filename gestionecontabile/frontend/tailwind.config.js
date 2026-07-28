/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      colors: {
        navy:  { DEFAULT: '#1D3557', light: '#EBF0F6', dark: '#2B4A72' },
        teal:  { DEFAULT: '#2A9D8F', light: '#E6F5F3' },
        coral: { DEFAULT: '#E76F51', light: '#FCF0EC' },
        amber: { DEFAULT: '#E8A020', light: '#FEF5E7' },
        sand:  { DEFAULT: '#F7F6F2' },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Helvetica', 'Arial', 'sans-serif'],
        mono: ['"SFMono-Regular"', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
