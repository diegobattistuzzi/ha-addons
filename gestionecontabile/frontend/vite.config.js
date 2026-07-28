import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    vue(),
    // Rende l'app installabile da cellulare (schermata Home) per l'accesso
    // mobile via QR/token - vedi Persons.vue "Genera accesso mobile". Path
    // relativi (start_url/scope '.') perche' l'app gira sia sotto il prefisso
    // di HA Ingress sia sulla porta pubblica dedicata (base: './' sotto),
    // quindi non ha un percorso assoluto fisso da dichiarare qui.
    VitePWA({
      registerType: 'autoUpdate',
      // Senza questi due il nuovo service worker resta "in attesa" finche' non
      // chiudi del tutto ogni scheda/istanza aperta della PWA, quindi un
      // deploy puo' sembrare "non arrivato" anche dopo un rebuild riuscito -
      // qui forziamo l'aggiornamento a prendere subito il controllo.
      workbox: {
        skipWaiting: true,
        clientsClaim: true,
      },
      manifest: {
        name: 'Spese di casa',
        short_name: 'Spese',
        description: 'Gestione spese familiari',
        start_url: '.',
        scope: './',
        display: 'standalone',
        background_color: '#F7F5F1',
        theme_color: '#1D3557',
        icons: [
          { src: 'pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512.png', sizes: '512x512', type: 'image/png' },
        ],
      },
    }),
  ],
  base: './',
  server: {
    port: 5173,
    proxy: {
      '/api':    'http://localhost:8099',
      '/health': 'http://localhost:8099',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
