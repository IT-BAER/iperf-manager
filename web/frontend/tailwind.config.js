/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0c0c0f',
        surface: {
          DEFAULT: '#121215',
          raised: '#19191d',
          hover: '#202025',
          active: '#28282e',
        },
        line: { DEFAULT: '#232328', bright: '#3a3a42' },
        fg: { DEFAULT: '#e8e8ec', 2: '#9898a0', 3: '#6a6a74', 4: '#484852' },
        accent: { DEFAULT: '#4b8df8', dim: '#3a7de6', subtle: 'rgba(75,141,248,0.08)' },
        ok: { DEFAULT: '#3ec96a', subtle: 'rgba(62,201,106,0.08)' },
        warn: { DEFAULT: '#e8a43a', subtle: 'rgba(232,164,58,0.08)' },
        err: { DEFAULT: '#e5534b', subtle: 'rgba(229,83,75,0.08)' },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'system-ui', 'sans-serif'],
        mono: ['"SF Mono"', '"Cascadia Code"', 'Consolas', '"Liberation Mono"', 'monospace'],
      },
      borderRadius: {
        sm: '6px',
        DEFAULT: '8px',
        lg: '12px',
      },
    },
  },
  plugins: [],
}

