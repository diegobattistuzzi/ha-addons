const STORAGE_KEY = 'casaspese_person_id'

export function getPersonId() {
  return localStorage.getItem(STORAGE_KEY) || ''
}

export function setPersonId(id) {
  localStorage.setItem(STORAGE_KEY, String(id))
}

export function clearPersonId() {
  localStorage.removeItem(STORAGE_KEY)
}
