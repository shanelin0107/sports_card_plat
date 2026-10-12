import type { Config } from 'tailwindcss';

export default {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        base: '#0B0F14',
        chrome: '#0E141B',
        panel: '#111821',
        raised: '#15202B',
        line: '#1E2A36',
        edge: '#263545',
        ink: '#E6EDF3',
        muted: '#9FB3C8',
        up: '#3DDC97',
        down: '#FF7A7A',
        warn: '#F5B841',
        link: '#7CC4FF',
      },
      fontFamily: {
        sans: ['"Space Grotesk"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config;
