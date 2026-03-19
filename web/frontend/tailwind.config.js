/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0d1117',
        surface: {
          DEFAULT: '#151b23',
          raised: '#212830',
          hover: '#262c36',
          active: '#2a313c',
        },
        line: { DEFAULT: '#3d444d', bright: '#656c76' },
        fg: { DEFAULT: '#f0f6fc', 2: '#c9d1d9', 3: '#9198a1', 4: '#656d76' },
        accent: { DEFAULT: '#4493f8', dim: '#1f6feb', subtle: 'rgba(56,139,253,0.10)' },
        ok: { DEFAULT: '#3fb950', subtle: 'rgba(46,160,67,0.15)' },
        warn: { DEFAULT: '#d29922', subtle: 'rgba(210,153,34,0.16)' },
        err: { DEFAULT: '#f85149', subtle: 'rgba(248,81,73,0.10)' },
        tab: { active: '#f78166' },
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

