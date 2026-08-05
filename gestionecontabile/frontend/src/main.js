import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router.js'
import './style.css'
import { initHaTheme } from './ha-theme.js'
import { i18n } from './i18n/index.js'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)

// Aspetta che il router risolva la navigazione iniziale (incluse le guardie in
// router.js, che salvano il token mobile letto da ?token= in localStorage)
// PRIMA di montare l'app: altrimenti il controllo di autenticazione di App.vue
// puo' partire senza token ancora salvato, ricevere un 401 dal backend e
// mostrare "accesso negato" anche con un link mobile perfettamente valido -
// un semplice problema di timing all'avvio, non un token scaduto.
router.isReady().then(() => {
  app.mount('#app')
  initHaTheme()
})
