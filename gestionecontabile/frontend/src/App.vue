<template>
  <div v-if="authState === 'checking'" class="boot-check"></div>

  <div v-else-if="authState === 'denied'" class="denied-page">
    <div class="denied-icon">🔒</div>
    <div class="denied-title">{{ t('app.denied.title') }}</div>
    <div class="denied-text">{{ isMobileRoute ? t('app.denied.mobileText') : t('app.denied.appText') }}</div>
  </div>

  <div v-else-if="isMobileRoute" class="mobile-shell">
    <main class="mobile-main">
      <RouterView />
    </main>
    <nav class="mobile-tabbar">
      <RouterLink to="/mobile/scan" class="mobile-tab"><span>📷</span>{{ t('app.nav.mobileScan') }}</RouterLink>
      <RouterLink to="/mobile/transactions" class="mobile-tab"><span>↕</span>{{ t('app.nav.transactions') }}</RouterLink>
    </nav>
  </div>

  <div v-else class="app-shell">
    <aside class="sidebar">
      <div class="sidebar-logo">
        <div class="logo-icon">🏠</div>
        <div>
          <div class="logo-name">{{ t('app.name') }}</div>
          <div class="logo-sub">{{ t('app.sub') }}</div>
        </div>
      </div>
      <nav class="sidebar-nav">
        <div class="nav-label">{{ t('app.navMain') }}</div>
        <RouterLink to="/dashboard"    class="nav-item"><span>▦</span>{{ t('app.nav.dashboard') }}</RouterLink>
        <RouterLink to="/transactions" class="nav-item"><span>↕</span>{{ t('app.nav.transactions') }}</RouterLink>
        <RouterLink to="/reports"      class="nav-item"><span>◈</span>{{ t('app.nav.reports') }}</RouterLink>
        <RouterLink to="/balance"      class="nav-item"><span>⚖</span>{{ t('app.nav.balance') }}</RouterLink>
        <RouterLink to="/documenti"    class="nav-item"><span>📄</span>{{ t('app.nav.documents') }}</RouterLink>
        <RouterLink to="/email"        class="nav-item"><span>📧</span>{{ t('app.nav.email') }}</RouterLink>
        <div class="nav-label" style="margin-top:16px">{{ t('app.navRegistry') }}</div>
        <RouterLink to="/persons"      class="nav-item"><span>◉</span>{{ t('app.nav.persons') }}</RouterLink>
        <RouterLink to="/accounts"     class="nav-item"><span>▣</span>{{ t('app.nav.accounts') }}</RouterLink>
        <RouterLink to="/categories"   class="nav-item"><span>◑</span>{{ t('app.nav.categories') }}</RouterLink>
        <div class="nav-label" style="margin-top:16px">{{ t('app.navConfig') }}</div>
        <RouterLink to="/setup"    class="nav-item"><span>✦</span>{{ t('app.nav.setup') }}</RouterLink>
        <RouterLink to="/guida"    class="nav-item"><span>❓</span>{{ t('app.nav.guida') }}</RouterLink>
      </nav>
      <div class="sidebar-footer">
        <span v-if="currentPerson" class="identity-row">
          {{ t('app.viewAs') }} <strong>{{ currentPerson.name }}</strong>
        </span>
        <span class="lang-row">
          <button
            v-for="l in locales"
            :key="l"
            class="lang-btn"
            :class="{ active: locale === l }"
            @click="changeLocale(l)"
          >{{ l.toUpperCase() }}</button>
        </span>
        <span>{{ month }}</span>
        <span style="color:rgba(255,255,255,.3)">v1.0.0</span>
      </div>
    </aside>
    <main class="main-area">
      <RouterView />
    </main>
    <IdentityPicker />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { api } from './api.js'
import { getPersonId } from './identity.js'
import { getMobileToken } from './mobileToken.js'
import { setLocale, SUPPORTED_LOCALES } from './i18n/index.js'
import IdentityPicker from './components/IdentityPicker.vue'

const { t, locale } = useI18n()
const locales = SUPPORTED_LOCALES
const route = useRoute()

// Le route /mobile/* sono la PWA installata sul telefono (vedi Persons.vue
// "Genera accesso mobile"): niente sidebar fissa da 220px pensata per
// desktop, solo il contenuto + una tabbar in basso. Chi ha un token mobile
// salvato resta sulla shell mobile anche se per qualche motivo si ritrova su
// una rotta non /mobile/* (vedi guardia in router.js): qui e' una seconda
// barriera, cosi' la sidebar con tutte le pagine del sito non compare mai
// nemmeno per un istante durante un redirect.
const isMobileRoute = computed(() => !!route.meta.mobile || !!getMobileToken())

const month = computed(() => new Date().toLocaleDateString(`${locale.value}-${locale.value.toUpperCase()}`, { month: 'long', year: 'numeric' }))
const currentPerson = ref(null)
const authState = ref('checking')

function changeLocale(l) {
  setLocale(l)
}

onMounted(async () => {
  // Verifica di autorizzazione prima di renderizzare l'app vera e propria:
  // il backend blocca le chiamate /api/* che non arrivano da Ingress HA ne'
  // portano un token mobile valido (vedi enforce_public_gateway_auth in
  // server.py). Senza questo controllo, un accesso negato mostrerebbe
  // comunque tutta la UI (sidebar, pagine) con ogni pannello vuoto/in errore
  // invece di una schermata di blocco chiara.
  try {
    await api.get('api/categories')
    authState.value = 'ok'
  } catch (e) {
    authState.value = e?.response?.status === 401 ? 'denied' : 'ok'
  }
  if (authState.value !== 'ok') return

  const personId = getPersonId()
  if (!personId) return
  try {
    const res = await api.get(`api/persons/${personId}`)
    currentPerson.value = res.data
  } catch {
    // profilo non trovato (es. eliminato): resta senza indicatore, IdentityPicker gestira' la richiesta
  }
})
</script>

<style scoped>
.app-shell { display:flex; height:100vh; overflow:hidden; }
.sidebar { width:220px; flex-shrink:0; background:#1D3557; color:#fff; display:flex; flex-direction:column; }
.sidebar-logo { display:flex; align-items:center; gap:10px; padding:24px 20px 20px; border-bottom:1px solid rgba(255,255,255,.1); }
.logo-icon { width:32px; height:32px; background:#2A9D8F; display:grid; place-items:center; font-size:16px; flex-shrink:0; }
.logo-name { font-size:15px; font-weight:600; }
.logo-sub { font-size:10px; color:rgba(255,255,255,.4); text-transform:uppercase; letter-spacing:.08em; }
.sidebar-nav { padding:20px 0; flex:1; overflow-y:auto; }
.nav-label { font-size:10px; letter-spacing:.12em; text-transform:uppercase; color:rgba(255,255,255,.3); padding:0 20px 8px; }
.nav-item { display:flex; align-items:center; gap:10px; padding:9px 20px; font-size:13.5px; color:rgba(255,255,255,.6); text-decoration:none; border-left:2px solid transparent; transition:background .12s,color .12s; }
.nav-item:hover { background:rgba(255,255,255,.06); color:rgba(255,255,255,.9); }
.nav-item.router-link-active { background:rgba(255,255,255,.1); color:#fff; border-left-color:#2A9D8F; }
.sidebar-footer { padding:16px 20px; border-top:1px solid rgba(255,255,255,.1); font-size:12px; color:rgba(255,255,255,.35); display:flex; flex-direction:column; gap:2px; }
.identity-row { color:rgba(255,255,255,.6); display:flex; align-items:center; gap:6px; margin-bottom:4px; }
.identity-row strong { color:#fff; }
.lang-row { display:flex; gap:6px; margin-bottom:4px; }
.lang-btn { background:none; border:1px solid rgba(255,255,255,.15); color:rgba(255,255,255,.5); font-size:10px; padding:2px 6px; cursor:pointer; font-family:inherit; letter-spacing:.04em; }
.lang-btn:hover { color:rgba(255,255,255,.85); border-color:rgba(255,255,255,.3); }
.lang-btn.active { background:#2A9D8F; border-color:#2A9D8F; color:#fff; }
.main-area { flex:1; overflow-y:auto; background:#F7F6F2; }

.mobile-shell { display:flex; flex-direction:column; height:100vh; overflow:hidden; }
.mobile-main { flex:1; overflow-y:auto; background:#F7F5F1; }
.mobile-tabbar { display:flex; border-top:1px solid #DDD9D0; background:#fff; padding-bottom:env(safe-area-inset-bottom); }
.mobile-tab { flex:1; display:flex; flex-direction:column; align-items:center; gap:2px; padding:8px 0; font-size:11px; color:#9A938C; text-decoration:none; }
.mobile-tab span { font-size:18px; }
.mobile-tab.router-link-active { color:#1D3557; font-weight:600; }

.boot-check { height:100vh; }

.denied-page { height:100vh; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:10px; padding:24px; text-align:center; background:#F7F6F2; }
.denied-icon { font-size:40px; }
.denied-title { font-size:16px; font-weight:600; color:#1D3557; }
.denied-text { font-size:13px; color:#5C5752; max-width:360px; line-height:1.5; }
</style>
