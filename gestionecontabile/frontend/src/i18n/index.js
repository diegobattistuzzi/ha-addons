import { createI18n } from 'vue-i18n'

const itModules = import.meta.glob('./locales/it/*.json', { eager: true })
const enModules = import.meta.glob('./locales/en/*.json', { eager: true })

function mergeMessages(modules) {
  const result = {}
  for (const path in modules) {
    Object.assign(result, modules[path].default)
  }
  return result
}

const it = mergeMessages(itModules)
const en = mergeMessages(enModules)

const STORAGE_KEY = 'casaspese.locale'
const SUPPORTED_LOCALES = ['it', 'en']

function detectLocale() {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved && SUPPORTED_LOCALES.includes(saved)) return saved
  const browser = (navigator.language || 'it').slice(0, 2)
  return SUPPORTED_LOCALES.includes(browser) ? browser : 'it'
}

export const i18n = createI18n({
  legacy: false,
  locale: detectLocale(),
  fallbackLocale: 'it',
  messages: { it, en },
})

export function setLocale(locale) {
  if (!SUPPORTED_LOCALES.includes(locale)) return
  i18n.global.locale.value = locale
  localStorage.setItem(STORAGE_KEY, locale)
  document.documentElement.setAttribute('lang', locale)
}

export function getLocale() {
  return i18n.global.locale.value
}

export { SUPPORTED_LOCALES }
