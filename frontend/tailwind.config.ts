import type { Config } from 'tailwindcss'

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: {
          950: '#060F1E',
          900: '#0A1628',
          800: '#0D1F3C',
          700: '#122040',
          600: '#1A2E52',
          500: '#1E3A6E',
          400: '#2D4E8A',
        },
        accent: {
          blue: '#1E6FD9',
          'blue-light': '#3B8BEF',
          'blue-dim': '#1559B0',
        },
        risk: {
          critical: '#EF4444',
          high: '#F97316',
          medium: '#F59E0B',
          low: '#10B981',
        },
        surface: {
          DEFAULT: '#F1F5F9',
          card: '#FFFFFF',
          muted: '#E2E8F0',
        },
      },
      fontFamily: {
        sans: ['IBM Plex Sans', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['IBM Plex Mono', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 3px 0 rgba(0,0,0,0.07), 0 1px 2px -1px rgba(0,0,0,0.07)',
        'card-hover': '0 4px 12px 0 rgba(0,0,0,0.10), 0 2px 4px -1px rgba(0,0,0,0.08)',
        'navy-glow': '0 0 0 2px rgba(30,111,217,0.4)',
      },
      animation: {
        'pulse-slow': 'pulse 2.5s cubic-bezier(0.4,0,0.6,1) infinite',
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-in': 'slideIn 0.25s ease-out',
        'particle': 'particle 1.5s linear infinite',
      },
      keyframes: {
        fadeIn: { from: { opacity: '0' }, to: { opacity: '1' } },
        slideIn: { from: { opacity: '0', transform: 'translateY(8px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
        particle: { '0%': { strokeDashoffset: '24' }, '100%': { strokeDashoffset: '0' } },
      },
    },
  },
  plugins: [],
} satisfies Config
