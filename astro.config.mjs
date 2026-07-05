import { defineConfig } from 'astro/config';

// Standalone static site for the family WC2026 sweepstake.
// Built by Cloudflare Pages on push; no SSR adapter needed.
export default defineConfig({
  site: 'https://wc26.jeansy.org',
  // Dev-only: let Tailscale MagicDNS hostnames reach the dev server so the
  // work-in-progress site can be previewed from any device on the tailnet.
  vite: {
    server: {
      allowedHosts: ['.ts.net'],
    },
  },
});
