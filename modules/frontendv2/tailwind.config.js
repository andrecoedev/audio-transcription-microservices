/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Semantic API for shared components; old utilities stay compatible.
        canvas: 'var(--usagi-canvas)',
        shell: 'var(--usagi-shell)',
        surface: 'var(--usagi-surface)',
        'surface-secondary': 'var(--usagi-surface-secondary)',
        ink: 'var(--usagi-ink)',
        muted: 'var(--usagi-muted)',
        success: 'var(--usagi-success)',
        warning: 'var(--usagi-warning)',
        danger: 'var(--usagi-danger)',
        info: 'var(--usagi-info)',
        primary: {
          50: 'rgb(var(--usagi-primary-soft-rgb) / <alpha-value>)',
          100: 'var(--usagi-primary-tint)',
          200: 'var(--usagi-primary-mid)',
          300: 'var(--usagi-primary-mid)',
          400: 'var(--usagi-primary)',
          500: 'var(--usagi-primary)',
          600: 'var(--usagi-primary)',
          700: 'var(--usagi-primary-hover)',
          800: 'var(--usagi-primary-hover)',
          900: 'rgb(var(--usagi-ink-rgb) / <alpha-value>)',
        },
        gray: {
          50: 'var(--usagi-surface-secondary)',
          100: 'var(--usagi-shell)',
          200: 'var(--usagi-border)',
          300: 'var(--usagi-control-border)',
          400: 'var(--usagi-muted)',
          500: 'var(--usagi-muted)',
          600: 'var(--usagi-text-secondary)',
          700: 'var(--usagi-text-secondary)',
          800: 'var(--usagi-ink)',
          900: 'rgb(var(--usagi-ink-rgb) / <alpha-value>)',
        },
      },
      boxShadow: { popover: 'var(--usagi-shadow-popover)' },
      borderRadius: {
        md: 'var(--usagi-radius-badge)', lg: 'var(--usagi-radius-control)',
        xl: 'var(--usagi-radius-modal)',
      },
      spacing: {
        1: 'var(--usagi-space-1)', 2: 'var(--usagi-space-2)',
        3: 'var(--usagi-space-3)', 4: 'var(--usagi-space-4)',
        6: 'var(--usagi-space-6)', 8: 'var(--usagi-space-8)',
        12: 'var(--usagi-space-12)',
      },
      fontSize: { xs: ['0.8125rem', { lineHeight: '1.25rem' }] },
      transitionDuration: { DEFAULT: 'var(--usagi-duration)' },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}
