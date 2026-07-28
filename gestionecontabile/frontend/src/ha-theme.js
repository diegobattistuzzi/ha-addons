// Adatta l'app a chiaro/scuro seguendo le preferenze del sistema (di solito
// coincide col tema HA quando l'utente lo tiene su "automatico").
//
// In precedenza si provava a leggere le CSS custom properties di HA
// (--primary-color ecc.) da window.parent.document, sotto assunzione che
// l'iframe di ingress fosse same-origin: nella pratica l'iframe di ingress ha
// l'attributo sandbox e senza il flag allow-same-origin l'accesso al parent
// viene bloccato come origine opaca, quindi quel meccanismo non si applicava
// mai (fallback silenzioso alla palette statica). prefers-color-scheme non
// richiede accesso cross-frame ed e' quindi affidabile.
const DARK_VARS = {
  '--bg': '#1C1C1E',
  '--surface': '#242426',
  '--surface-2': '#2C2C2E',
  '--border': '#3A3A3C',
  '--text': '#F2F1EE',
  '--text-2': '#B8B3AD',
  '--text-3': '#7D7972',
}

function applyDark(isDark) {
  const root = document.documentElement.style
  if (isDark) {
    for (const [prop, value] of Object.entries(DARK_VARS)) root.setProperty(prop, value)
  } else {
    for (const prop of Object.keys(DARK_VARS)) root.removeProperty(prop)
  }
}

export function initHaTheme() {
  const mq = window.matchMedia('(prefers-color-scheme: dark)')
  applyDark(mq.matches)
  mq.addEventListener('change', e => applyDark(e.matches))
}
