/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: '#fbf7f2',
        paper: '#ffffff',
        panel: 'rgba(255, 255, 255, 0.94)',
        ink: '#2f2a24',
        muted: '#82766a',
        line: '#eadfd4',
        'line-strong': '#d9c4b4',
        accent: '#d97745',
        'accent-soft': '#fff0e6',
        'accent-line': '#e7b08d',
        green: '#6f8f52',
        amber: '#d97745',
        red: '#b85c5c',
        violet: '#a4765c',
      },
      fontFamily: {
        sans: ['Candara', 'Aptos', 'Microsoft YaHei', 'sans-serif'],
        serif: ['Cambria', 'Georgia', 'serif'],
        mono: ['Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
