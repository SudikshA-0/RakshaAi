/** RakshaAI design system — a warm, light, operational fintech palette.
 *  Colour is used for MEANING (risk / status), never decoration.
 */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        // --- surfaces ---
        paper: '#FFFFFF', // primary surface
        canvas: '#F5F5F3', // app background (Soft Gray)
        cream: { DEFAULT: '#FFF1D1', soft: '#FFF8E9', deep: '#F3E2B4' }, // Warm Cream

        // --- lines ---
        line: { DEFAULT: '#E5E5E0', strong: '#D6D6CF' }, // Border Gray

        // --- text / dark surfaces ---
        ink: {
          DEFAULT: '#151515', // Deep Ink — primary text + nav
          950: '#0D0D0D',
          900: '#151515',
          850: '#1D1D1C',
          800: '#242423',
          700: '#33322F',
          600: '#454541',
          500: '#5C5B56',
        },
        muted: '#4B5563', // Slate — secondary text
        faint: '#8A8B85', // tertiary text / icons

        // --- semantic status hues (risk / actions) ---
        signal: { DEFAULT: '#DF301C', soft: '#FBE3DE', mid: '#EFA79C', deep: '#A81F0F' }, // Signal Red
        warn: { DEFAULT: '#FF9100', soft: '#FFEFD6', mid: '#FFCB80', deep: '#A85E00' }, // Action Orange
        hold: { DEFAULT: '#E5590C', soft: '#FBE6D8', deep: '#9E3D06' }, // burnt orange (review)
        trust: { DEFAULT: '#00B7CD', soft: '#DFF5F8', mid: '#7FD4E1', deep: '#0A7080' }, // Electric Cyan
      },
      boxShadow: {
        card: '0 1px 2px rgba(21,21,21,0.04)',
        raise: '0 1px 3px rgba(21,21,21,0.06), 0 8px 22px -14px rgba(21,21,21,0.14)',
        menu: '0 8px 28px -10px rgba(21,21,21,0.22), 0 2px 6px -2px rgba(21,21,21,0.10)',
        drawer: '-16px 0 48px -20px rgba(21,21,21,0.28)',
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'row-in': {
          '0%': { backgroundColor: 'rgba(0,183,205,0.12)' },
          '100%': { backgroundColor: 'rgba(0,183,205,0)' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.35s cubic-bezier(0.16,1,0.3,1) both',
        'row-in': 'row-in 1.4s ease-out both',
      },
    },
  },
  plugins: [],
}
