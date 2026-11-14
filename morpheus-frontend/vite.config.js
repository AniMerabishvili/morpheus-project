import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'favicon.ico'],
      manifest: {
        name: 'Morpheus Dream Analytics',
        short_name: 'Morpheus',
        description: 'Transform your dreams into insights',
        start_url: '/',
        display: 'standalone',
        background_color: '#0f0f0f',
        theme_color: '#FFDE6E',
        // Installed app shows up in the phone's share sheet: share a note from
        // Samsung Notes / Keep / Obsidian → it opens in Morpheus ready to analyse.
        share_target: {
          action: '/share',
          method: 'GET',
          params: { title: 'title', text: 'text', url: 'url' },
        },
        icons: [
          {
            src: '/icons/morpheus192.png',
            sizes: '192x192',
            type: 'image/png',
          },
          {
            src: '/icons/morpheus512.png',
            sizes: '512x512',
            type: 'image/png',
          },
          {
            src: '/icons/morpheus512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any maskable',
          },
        ],
      },
    }),
  ],
  server: {
    allowedHosts: true,
    proxy: {
      '/v1': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
  preview: {
    allowedHosts: true,
  },
})
