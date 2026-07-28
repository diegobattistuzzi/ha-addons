const STORAGE_KEY = 'casaspese_mobile_token'

export function getMobileToken() {
  return localStorage.getItem(STORAGE_KEY) || ''
}

export function setMobileToken(token) {
  localStorage.setItem(STORAGE_KEY, token)
}

export function clearMobileToken() {
  localStorage.removeItem(STORAGE_KEY)
}
