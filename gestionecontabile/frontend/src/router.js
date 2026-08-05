import { createRouter, createWebHashHistory } from 'vue-router'
import { setMobileToken, getMobileToken } from './mobileToken.js'

const routes = [
  { path: '/',             redirect: '/dashboard' },
  { path: '/dashboard',    component: () => import('./views/Dashboard.vue') },
  { path: '/transactions', component: () => import('./views/Transactions.vue') },
  { path: '/persons',      component: () => import('./views/Persons.vue') },
  { path: '/accounts',     component: () => import('./views/Accounts.vue') },
  { path: '/categories',   component: () => import('./views/Categories.vue') },
  { path: '/rules',        component: () => import('./views/Rules.vue') },
  { path: '/reports',      component: () => import('./views/Reports.vue') },
  { path: '/assistant',    component: () => import('./views/Assistant.vue') },
  { path: '/balance',      component: () => import('./views/Balance.vue') },
  { path: '/documenti',    component: () => import('./views/Documents.vue') },
  { path: '/email',        component: () => import('./views/EmailReceipts.vue') },
  { path: '/setup',        component: () => import('./views/setup/SetupWizard.vue') },
  { path: '/guida',        component: () => import('./views/Guida.vue') },
  { path: '/mobile/link',  redirect: '/mobile/scan' },
  { path: '/mobile/scan',         meta: { mobile: true }, component: () => import('./views/ReceiptCapture.vue') },
  { path: '/mobile/transactions', meta: { mobile: true }, component: () => import('./views/MobileTransactions.vue') },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// Il link/QR generato da Persons -> "Genera accesso mobile" punta a
// /mobile/link?token=... : lo salviamo subito e lo togliamo dall'URL, cosi'
// non resta visibile in cronologia/condivisioni accidentali del link.
router.beforeEach(to => {
  if (to.query.token) {
    setMobileToken(String(to.query.token))
    const { token, ...rest } = to.query
    return { path: to.path, query: rest }
  }
  // Chi ha un token mobile salvato resta CONFINATO alle rotte /mobile/*, sempre:
  // l'app installata come PWA riparte dalla home ('start_url: .', vedi
  // vite.config.js) e non dal link col token, quindi al rilancio finirebbe su
  // '/dashboard' - autenticata comunque (api.js manda il token come Bearer su
  // ogni chiamata), ma con la sidebar e tutte le pagine del sito intero invece
  // della sola vista mobile. Senza questo redirect chiunque riceva un link
  // "Genera accesso mobile" (pensato solo per scansionare scontrini/vedere le
  // proprie transazioni) si ritroverebbe con accesso a conti, bilancio,
  // persone, categorie ecc.
  if (getMobileToken() && !to.path.startsWith('/mobile')) {
    return '/mobile/scan'
  }
})

export default router
