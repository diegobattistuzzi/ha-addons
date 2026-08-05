import axios from 'axios'
import { getPersonId } from './identity.js'
import { getMobileToken } from './mobileToken.js'

// HA Ingress serve l'addon sotto /api/hassio_ingress/TOKEN/ - la base va
// calcolata come origin+pathname (es. https://homeassistant.local/api/hassio_ingress/ABC123/).
//
// NON usare document.baseURI: include l'hash fragment se e' gia' presente al
// primissimo caricamento della pagina (es. aprendo un link mobile tipo
// .../#/mobile/link?token=...). Axios concatena le stringhe senza fare una
// vera risoluzione URL, quindi un baseURL con "#" dentro produce un url tipo
// "https://host/#/mobile/scan/api/accounts" - che il browser interpreta come
// path "/" + frammento "#/mobile/scan/api/accounts" (mai inviato al server):
// ogni chiamata finirebbe quindi su "/" invece che sull'endpoint vero.
// location.pathname esclude sempre hash e query, quindi non ha questo problema.
//
// Le chiamate axios usano path relativi (senza / iniziale) tipo 'api/setup/status'
// che il browser risolve correttamente contro questa base.
//
// In sviluppo locale: origin+pathname = http://localhost:5173/ → Vite proxia /api/* → :8099 ✓

export const api = axios.create({ baseURL: window.location.origin + window.location.pathname })

// Il backend riconosce automaticamente l'utente HA loggato (se ogni persona ha
// un account HA separato). Come fallback, quando l'utente ha scelto manualmente
// il proprio profilo (vedi identity.js), lo comunichiamo al backend con questo
// header cosi' il filtro delle spese personali funziona anche condividendo un
// unico account HA.
// La PWA installata su un dispositivo fuori dalla rete HA si autentica con un
// token per-persona (generato da Persons -> "Genera accesso mobile" e
// consegnato via QR/link) invece dell'header X-Person-Id, che e' fidato solo
// sulla rete locale/Ingress - vedi access.py per la risoluzione lato backend.
api.interceptors.request.use(config => {
  const mobileToken = getMobileToken()
  if (mobileToken) {
    config.headers['Authorization'] = `Bearer ${mobileToken}`
    return config
  }
  const personId = getPersonId()
  if (personId) config.headers['X-Person-Id'] = personId
  return config
})

// Un <a href="api/documents/123/download"> naviga fuori da axios, quindi non
// porta ne' l'header Authorization (token mobile PWA) ne' X-Person-Id: il
// backend risponde 401 (vedi enforce_public_gateway_auth in server.py) a
// chiunque non abbia anche l'header x-ingress-path genuino di HA. Passando
// dall'istanza axios sopra il download riceve gli stessi header di ogni altra
// chiamata API; il file arriva come blob e viene "scaricato" creando un <a>
// temporaneo con URL.createObjectURL, senza mai esporre un link diretto.
export async function downloadFile(path, filename) {
  const res = await api.get(path, { responseType: 'blob' })
  let name = filename
  const disposition = res.headers['content-disposition']
  if (!name && disposition) {
    const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition)
    if (match) name = decodeURIComponent(match[1])
  }
  const blobUrl = URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = name || 'download'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(blobUrl)
}

export default api
