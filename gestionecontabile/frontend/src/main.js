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
app.mount('#app')

initHaTheme()
