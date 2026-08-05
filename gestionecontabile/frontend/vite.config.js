import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import pkg from './package.json' with { type: 'json' }

export default defineConfig({
  // Espone la versione di package.json in App.vue (footer sidebar) come
  // __APP_VERSION__: va tenuta allineata a config.yaml (versione dell'add-on
  // HA) ad ogni release, cosi' un domani un disallineamento si vede subito
  // nell'app invece di scoprirlo per caso confrontando due file a mano.
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
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
        // opencv.js/jscanify (public/vendor) pesano ~8MB e servono solo alla
        // schermata di scansione scontrini: esclusi dal precache (altrimenti
        // finirebbero scaricati eagerly all'installazione della PWA) e messi
        // in cache runtime solo alla prima richiesta effettiva.
        globIgnores: ['vendor/**'],
        runtimeCaching: [
          {
            urlPattern: /\/vendor\/(opencv|jscanify)\.js$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'receipt-scanner-vendor',
              expiration: { maxEntries: 2 },
            },
          },
        ],
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
