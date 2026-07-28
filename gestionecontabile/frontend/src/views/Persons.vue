<template>
  <div>
    <div class="topbar">
      <div class="topbar-title">{{ t('persons.title') }}</div>
      <div class="topbar-actions">
        <button class="btn btn-sm" @click="syncHa" :disabled="syncingHa">
          {{ syncingHa ? '...' : t('persons.importFromHa') }}
        </button>
        <button class="btn btn-primary btn-sm" @click="openAdd">{{ t('persons.addPerson') }}</button>
      </div>
    </div>

    <div class="content">
      <div v-if="haMsg" class="banner" :class="haMsg.type">{{ haMsg.text }}</div>

      <div v-if="haWhoAmI?.haUserId" class="banner ok identity-banner">
        {{ t('persons.haIdentityBannerPrefix') }} <strong>{{ haWhoAmI.haUserDisplayName || haWhoAmI.haUserName || haWhoAmI.haUserId }}</strong>.
        {{ t('persons.haIdentityBannerSuffix') }}
      </div>

      <div v-if="loading" class="empty">{{ t('common.loading') }}</div>
      <div v-else-if="error" class="empty error-msg">{{ error }}</div>
      <div v-else-if="!persons.length" class="empty">
        {{ t('persons.noPersons') }}
      </div>

      <div v-else class="person-grid">
        <div v-for="p in persons" :key="p.id" class="person-card">
          <div class="person-avatar" :style="{ background: p.color || '#1D3557' }">
            {{ initials(p.name) }}
          </div>
          <div class="person-info">
            <div class="person-name">{{ p.name }}</div>
            <div class="person-email">{{ p.email || '—' }}</div>
            <div v-if="p.isPrimary" class="person-badge">{{ t('persons.primaryBadge') }}</div>
            <div v-if="p.ha_user_id && p.ha_user_id === haWhoAmI?.haUserId" class="person-badge ha-linked">{{ t('persons.haLinkedYou') }}</div>
            <div v-else-if="p.ha_user_id" class="person-badge">{{ t('persons.haLinkedOther') }}</div>
            <div v-if="p.imap_password_set" class="imap-status">
              {{ t('persons.imapActive') }}
              <span v-if="p.imap_last_checked_at">{{ t('persons.lastCheck', { date: formatDate(p.imap_last_checked_at) }) }}</span>
              <span v-else>{{ t('persons.awaitingFirstCheck') }}</span>
            </div>
          </div>
          <div class="person-actions">
            <button v-if="haWhoAmI?.haUserId && p.ha_user_id !== haWhoAmI.haUserId"
              class="btn-icon" :title="t('persons.linkHaTitle')" @click="linkHaUser(p)">🔗</button>
            <button v-if="p.imap_password_set" class="btn-icon" :title="t('persons.pollNowTitle')" :disabled="pollingId === p.id" @click="pollNow(p)">
              {{ pollingId === p.id ? '...' : '🔄' }}
            </button>
            <button v-if="p.imap_password_set" class="btn-icon" :title="t('persons.backfillTitle')" @click="openBackfill(p)">📧</button>
            <button class="btn-icon" :title="t('persons.mobileAccessTitle')" @click="openMobileAccess(p)">📱</button>
            <button class="btn-icon" @click="openEdit(p)">✎</button>
            <button class="btn-icon danger" @click="del(p)">✕</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal add/edit -->
    <div v-if="showModal" class="modal-backdrop" @click.self="showModal=false">
      <div class="modal">
        <div class="modal-header">
          <span>{{ editId ? t('persons.editPerson') : t('persons.newPerson') }}</span>
          <button class="btn-icon" @click="showModal=false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="label">{{ t('persons.nameLabel') }}</label>
            <input class="input" v-model="form.name" :placeholder="t('persons.namePlaceholder')" autofocus />
          </div>
          <div class="form-group">
            <label class="label">{{ t('persons.emailLabel') }}</label>
            <input class="input" v-model="form.email" :placeholder="t('persons.emailPlaceholder')" />
          </div>
          <div class="form-group">
            <label class="label">{{ t('persons.colorLabel') }}</label>
            <div class="color-row">
              <div v-for="c in colors" :key="c"
                class="color-dot" :style="{ background: c }"
                :class="{ selected: form.color === c }"
                @click="form.color = c" />
            </div>
          </div>
          <label class="check">
            <input type="checkbox" v-model="form.isPrimary" />
            {{ t('persons.primaryPersonCheck') }}
          </label>

          <div class="section-divider">{{ t('persons.emailSectionDivider') }}</div>
          <div class="form-row">
            <div class="form-group">
              <label class="label">{{ t('persons.imapServerLabel') }}</label>
              <input class="input" v-model="form.imapHost" :placeholder="t('persons.imapHostPlaceholder')" />
            </div>
            <div class="form-group">
              <label class="label">{{ t('persons.portLabel') }}</label>
              <input class="input" type="number" v-model="form.imapPort" placeholder="993" />
            </div>
          </div>
          <div class="form-group">
            <label class="label">{{ t('persons.userLabel') }}</label>
            <input class="input" v-model="form.imapUsername" :placeholder="t('persons.userPlaceholder')" />
          </div>
          <div class="form-group">
            <label class="label">{{ t('persons.passwordLabel') }} {{ editId && form.imapPasswordSet ? t('persons.passwordKeepHint') : '' }}</label>
            <input class="input" type="password" v-model="form.imapPassword" placeholder="••••••••" autocomplete="new-password" />
          </div>
          <label class="check">
            <input type="checkbox" v-model="form.imapUseSsl" />
            {{ t('persons.sslCheck') }}
          </label>

          <div v-if="formError" class="form-error">{{ formError }}</div>
        </div>
        <div class="modal-footer">
          <button class="btn" @click="showModal=false">{{ t('common.cancel') }}</button>
          <button class="btn btn-primary" @click="save" :disabled="saving">
            {{ saving ? '...' : t('common.save') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Modal backfill email -->
    <div v-if="showBackfill" class="modal-backdrop" @click.self="showBackfill=false">
      <div class="modal">
        <div class="modal-header">
          <span>{{ t('persons.backfillModalTitle', { name: backfillPerson?.name }) }}</span>
          <button class="btn-icon" @click="showBackfill=false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <div class="form-group">
              <label class="label">{{ t('persons.dateFromLabel') }}</label>
              <input class="input" type="date" v-model="backfillForm.dateFrom" />
            </div>
            <div class="form-group">
              <label class="label">{{ t('persons.dateToLabel') }}</label>
              <input class="input" type="date" v-model="backfillForm.dateTo" />
            </div>
          </div>
          <div class="form-group">
            <label class="label">{{ t('persons.sendersLabel') }}</label>
            <input class="input" v-model="backfillForm.senders" :placeholder="t('persons.sendersPlaceholder')" />
          </div>
          <div class="form-group">
            <label class="label">{{ t('persons.subjectKeywordsLabel') }}</label>
            <input class="input" v-model="backfillForm.subjectKeywords" :placeholder="t('persons.subjectKeywordsPlaceholder')" />
            <div class="field-hint">{{ t('persons.subjectKeywordsHint') }}</div>
          </div>
          <div v-if="backfilling" class="backfill-progress">
            <div class="backfill-stage">{{ backfillStageLabel }}</div>
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: backfillPercent + '%' }"></div>
            </div>
          </div>
          <div v-if="backfillResult" class="banner" :class="backfillResult.error ? 'err' : 'ok'">
            <template v-if="backfillResult.error">{{ backfillResult.error }}</template>
            <template v-else>
              {{ t('persons.backfillFoundResult', { found: backfillResult.found, scanned: backfillResult.scanned, matched: backfillResult.matched, pending: backfillResult.pending }) }}
              <div v-if="backfillResult.truncated" class="backfill-truncated">
                {{ t('persons.backfillTruncatedWarning', { totalFound: backfillResult.totalFound, scanned: backfillResult.scanned }) }}
              </div>
            </template>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn" @click="showBackfill=false">{{ t('common.close') }}</button>
          <button class="btn btn-primary" @click="runBackfill" :disabled="backfilling">
            {{ backfilling ? t('persons.scanningInProgress') : t('persons.startScan') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Modal accesso mobile (QR + gestione token) -->
    <div v-if="showMobileAccess" class="modal-backdrop" @click.self="showMobileAccess=false">
      <div class="modal">
        <div class="modal-header">
          <span>{{ t('persons.mobileAccessModalTitle', { name: mobileAccessPerson?.name }) }}</span>
          <button class="btn-icon" @click="showMobileAccess=false">✕</button>
        </div>
        <div class="modal-body">
          <div v-if="!publicUrlConfigured" class="banner err">
            {{ t('persons.mobileAccessNoPublicUrl') }}
          </div>

          <div class="form-group">
            <label class="label">{{ t('persons.mobileAccessLabelLabel') }}</label>
            <input class="input" v-model="newTokenLabel" :placeholder="t('persons.mobileAccessLabelPlaceholder')" />
          </div>
          <button class="btn btn-primary" @click="generateMobileToken" :disabled="generatingToken">
            {{ generatingToken ? '...' : t('persons.mobileAccessGenerate') }}
          </button>

          <div v-if="newTokenQr" class="qr-box">
            <img :src="newTokenQr" class="qr-image" />
            <input class="input" readonly :value="newTokenUrl" @click="$event.target.select()" />
            <div class="field-hint">{{ t('persons.mobileAccessQrHint') }}</div>
          </div>

          <div class="section-divider">{{ t('persons.mobileAccessListTitle') }}</div>
          <div v-if="!mobileTokens.length" class="empty">{{ t('persons.mobileAccessNoTokens') }}</div>
          <div v-else class="token-list">
            <div v-for="tk in mobileTokens" :key="tk.id" class="token-row">
              <div class="token-info">
                <div class="token-label">{{ tk.label || t('persons.mobileAccessUnlabeled') }}</div>
                <div class="token-meta">
                  {{ t('persons.mobileAccessCreated', { date: formatDate(tk.created_at) }) }}
                  <template v-if="tk.last_used_at"> · {{ t('persons.mobileAccessLastUsed', { date: formatDate(tk.last_used_at) }) }}</template>
                </div>
              </div>
              <button class="btn-icon danger" :title="t('persons.mobileAccessRevokeTitle')" @click="revokeMobileToken(tk)">✕</button>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn" @click="showMobileAccess=false">{{ t('common.close') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'
import { getPersonId } from '../identity.js'

const { t } = useI18n()

const persons    = ref([])
const loading    = ref(true)
const error      = ref('')
const syncingHa  = ref(false)
const haMsg      = ref(null)
const haWhoAmI   = ref(null)
const showModal  = ref(false)
const saving     = ref(false)
const formError  = ref('')
const editId     = ref(null)

const colors = ['#1D3557','#2A9D8F','#E76F51','#E8A020','#7B2D8B','#457B9D','#606C38','#C1121F']

const emptyForm = () => ({
  name: '', email: '', color: '#1D3557', isPrimary: false,
  imapHost: '', imapPort: '', imapUsername: '', imapPassword: '', imapUseSsl: true, imapPasswordSet: false,
})
const form = ref(emptyForm())

const pollingId = ref(null)

function formatDate(value) {
  if (!value) return '—'
  return new Date(value.replace(' ', 'T') + 'Z').toLocaleString('it-IT')
}

async function pollNow(p) {
  pollingId.value = p.id
  try {
    const { data } = await api.post(`api/persons/${p.id}/email-poll-now`)
    if (data.baseline) {
      alert(t('persons.pollBaselineMsg'))
    } else {
      alert(t('persons.pollResultMsg', { checked: data.checked, matched: data.matched, pending: data.pending }))
    }
    load()
  } catch (e) {
    alert(e?.response?.data?.error || t('persons.pollError'))
  } finally {
    pollingId.value = null
  }
}

const showBackfill    = ref(false)
const backfillPerson  = ref(null)
const backfilling     = ref(false)
const backfillResult  = ref(null)
const backfillForm    = ref({ dateFrom: '', dateTo: '', senders: 'paypal.com, amazon.it' })
const backfillStage    = ref('')
const backfillProgress = ref({ scanned: 0, total: 0 })

const backfillStageLabel = computed(() => {
  if (backfillStage.value === 'connecting') return t('persons.stageConnecting')
  if (backfillStage.value === 'searching') return t('persons.stageSearching')
  if (backfillStage.value === 'scanning') {
    const { scanned, total } = backfillProgress.value
    return t('persons.stageScanning', { scanned, total })
  }
  return t('persons.stageStarting')
})

const backfillPercent = computed(() => {
  const { scanned, total } = backfillProgress.value
  if (!total) return backfillStage.value ? 5 : 0
  return Math.min(100, Math.round((scanned / total) * 100))
})

function initials(name) {
  return (name || '').split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.get('api/persons')
    persons.value = res.data.map(p => ({ ...p, isPrimary: !!p.is_primary }))
  } catch (e) {
    error.value = e?.response?.data?.error || e.message || t('persons.loadError')
  } finally {
    loading.value = false
  }
}

async function loadHaWhoAmI() {
  try {
    const res = await api.get('api/ha/whoami')
    haWhoAmI.value = res.data
  } catch {
    haWhoAmI.value = null
  }
}

async function linkHaUser(p) {
  if (!haWhoAmI.value?.haUserId) return
  try {
    await api.put(`api/persons/${p.id}`, { haUserId: haWhoAmI.value.haUserId })
    load()
  } catch (e) {
    alert(e?.response?.data?.error || t('persons.linkHaError'))
  }
}

function openAdd() {
  form.value = emptyForm()
  editId.value = null
  formError.value = ''
  showModal.value = true
}

function openEdit(p) {
  form.value = {
    name: p.name, email: p.email || '', color: p.color || '#1D3557', isPrimary: !!p.isPrimary,
    imapHost: p.imap_host || '', imapPort: p.imap_port || '', imapUsername: p.imap_username || '',
    imapPassword: '', imapUseSsl: p.imap_use_ssl !== 0, imapPasswordSet: !!p.imap_password_set,
  }
  editId.value = p.id
  formError.value = ''
  showModal.value = true
}

async function save() {
  formError.value = ''
  if (!form.value.name.trim()) { formError.value = t('persons.nameRequired'); return }
  saving.value = true
  try {
    const payload = { ...form.value }
    // non sovrascrivere la password salvata se il campo e' stato lasciato vuoto in modifica
    if (editId.value && !payload.imapPassword) delete payload.imapPassword
    if (editId.value) {
      await api.put(`api/persons/${editId.value}`, payload)
    } else {
      await api.post('api/persons', payload)
    }
    showModal.value = false
    load()
  } catch (e) {
    formError.value = e?.response?.data?.error || e.message || t('persons.saveError')
  } finally {
    saving.value = false
  }
}

function openBackfill(p) {
  backfillPerson.value = p
  backfillResult.value = null
  // Di default limita agli ultimi 12 mesi: senza un intervallo la ricerca IMAP
  // non applica alcun filtro data e scansiona l'intera cronologia della casella.
  // Resta comunque modificabile/svuotabile per una ricerca senza limiti.
  const oneYearAgo = new Date()
  oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1)
  backfillForm.value = {
    dateFrom: oneYearAgo.toISOString().slice(0, 10),
    dateTo: '',
    senders: 'paypal.com, amazon.it',
    subjectKeywords: 'conferma ordine, ordine confermato, ricevuta, fattura, pagamento effettuato, hai pagato, order confirmation, payment receipt, your receipt, invoice',
  }
  showBackfill.value = true
}

function handleBackfillSseEvent(eventType, payload) {
  if (eventType === 'progress') {
    backfillStage.value = payload.stage
    if (payload.stage === 'scanning') backfillProgress.value = { scanned: payload.scanned, total: payload.total }
  } else if (eventType === 'error') {
    backfillResult.value = { error: payload.detail }
    backfilling.value = false
  } else if (eventType === 'done') {
    backfillResult.value = payload
    backfilling.value = false
  }
}

async function runBackfill() {
  backfilling.value = true
  backfillResult.value = null
  backfillStage.value = ''
  backfillProgress.value = { scanned: 0, total: 0 }
  try {
    const senders = backfillForm.value.senders.split(',').map(s => s.trim()).filter(Boolean)
    const subjectKeywords = backfillForm.value.subjectKeywords.split(',').map(s => s.trim()).filter(Boolean)

    const headers = { 'Content-Type': 'application/json' }
    const personId = getPersonId()
    if (personId) headers['X-Person-Id'] = personId

    const res = await fetch(new URL(`api/persons/${backfillPerson.value.id}/email-backfill-stream`, document.baseURI), {
      method: 'POST',
      headers,
      body: JSON.stringify({
        senders,
        subjectKeywords,
        dateFrom: backfillForm.value.dateFrom || null,
        dateTo: backfillForm.value.dateTo || null,
      }),
    })
    if (!res.ok || !res.body) throw new Error(t('persons.httpError', { status: res.status }))

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let streamDone = false
    while (!streamDone) {
      const { value, done } = await reader.read()
      streamDone = done
      if (value) buffer += decoder.decode(value, { stream: true })

      let sepIndex
      while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
        const rawEvent = buffer.slice(0, sepIndex)
        buffer = buffer.slice(sepIndex + 2)

        let eventType = 'message'
        let dataLine = ''
        for (const line of rawEvent.split('\n')) {
          if (line.startsWith('event:')) eventType = line.slice(6).trim()
          else if (line.startsWith('data:')) dataLine += line.slice(5).trim()
        }
        if (!dataLine) continue
        handleBackfillSseEvent(eventType, JSON.parse(dataLine))
      }
    }
  } catch (e) {
    backfillResult.value = { error: e.message || t('persons.backfillScanError') }
    backfilling.value = false
  }
}

async function del(p) {
  if (!confirm(t('persons.deleteConfirm', { name: p.name }))) return
  try {
    await api.delete(`api/persons/${p.id}`)
    load()
  } catch (e) {
    alert(e?.response?.data?.error || t('persons.deleteError'))
  }
}

const showMobileAccess    = ref(false)
const mobileAccessPerson  = ref(null)
const mobileTokens        = ref([])
const newTokenLabel       = ref('')
const generatingToken     = ref(false)
const newTokenQr          = ref('')
const newTokenUrl         = ref('')
const publicUrlConfigured = ref(true)

async function loadMobileTokens(personId) {
  try {
    const { data } = await api.get('api/mobile-tokens', { params: { personId } })
    // I token revocati non servono più in lista (niente da revocare, niente da
    // riusare): mostrarli come righe morte è solo rumore per chi gestisce gli accessi.
    mobileTokens.value = data.filter(tk => !tk.revoked_at)
  } catch {
    mobileTokens.value = []
  }
}

function openMobileAccess(p) {
  mobileAccessPerson.value = p
  newTokenLabel.value = ''
  newTokenQr.value = ''
  newTokenUrl.value = ''
  publicUrlConfigured.value = true
  showMobileAccess.value = true
  loadMobileTokens(p.id)
}

async function generateMobileToken() {
  generatingToken.value = true
  try {
    const { data } = await api.post('api/mobile-tokens', {
      personId: mobileAccessPerson.value.id,
      label: newTokenLabel.value.trim() || null,
    })
    if (!data.url) {
      publicUrlConfigured.value = false
      newTokenQr.value = ''
      newTokenUrl.value = ''
    } else {
      publicUrlConfigured.value = true
      newTokenUrl.value = data.url
      const QRCode = (await import('qrcode')).default
      newTokenQr.value = await QRCode.toDataURL(data.url, { width: 240, margin: 1 })
    }
    loadMobileTokens(mobileAccessPerson.value.id)
  } catch (e) {
    alert(e?.response?.data?.detail || t('persons.mobileAccessGenerateError'))
  } finally {
    generatingToken.value = false
  }
}

async function revokeMobileToken(tk) {
  if (!confirm(t('persons.mobileAccessRevokeConfirm'))) return
  try {
    await api.delete(`api/mobile-tokens/${tk.id}`)
    loadMobileTokens(mobileAccessPerson.value.id)
  } catch (e) {
    alert(e?.response?.data?.detail || t('persons.mobileAccessRevokeError'))
  }
}

async function syncHa() {
  syncingHa.value = true
  haMsg.value = null
  try {
    const res = await api.post('api/ha/sync-persons')
    haMsg.value = { type: 'ok', text: t('persons.haSyncSuccess', { count: res.data.imported }) }
    load()
  } catch (e) {
    haMsg.value = { type: 'err', text: e?.response?.data?.error || t('persons.haSyncError') }
  } finally {
    syncingHa.value = false
    setTimeout(() => { haMsg.value = null }, 4000)
  }
}

onMounted(() => { load(); loadHaWhoAmI() })
</script>

<style scoped>
.topbar { background:#fff; border-bottom:1px solid #DDD9D0; padding:0 28px; height:56px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10; }
.topbar-title { font-size:15px; font-weight:600; }
.topbar-actions { display:flex; gap:8px; }

.content { padding:28px; max-width:900px; }

.banner { padding:10px 16px; font-size:13px; margin-bottom:16px; border:1px solid; }
.banner.ok  { background:#E6F5F3; color:#2A9D8F; border-color:#2A9D8F; }
.banner.err { background:#FCF0EC; color:#E76F51; border-color:#E76F51; }
.identity-banner { line-height:1.5; }
.person-badge.ha-linked { background:#E6F5F3; color:#2A9D8F; }

.empty { text-align:center; padding:60px; color:#9A938C; font-size:13px; }
.error-msg { color:#E76F51; }

.person-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(260px,1fr)); gap:12px; }
.person-card { background:#fff; border:1px solid #DDD9D0; padding:16px; display:flex; align-items:center; gap:14px; }
.person-avatar { width:44px; height:44px; border-radius:0; display:grid; place-items:center; font-size:15px; font-weight:700; color:#fff; flex-shrink:0; }
.person-info { flex:1; min-width:0; }
.person-name  { font-size:14px; font-weight:600; }
.person-email { font-size:12px; color:#9A938C; margin-top:2px; }
.person-badge { display:inline-block; margin-top:5px; padding:2px 7px; font-size:10px; background:#EBF0F6; color:#1D3557; letter-spacing:.04em; }
.imap-status { font-size:11px; color:#9A938C; margin-top:4px; }
.person-actions { display:flex; flex-direction:column; gap:4px; }

.btn { display:inline-flex; align-items:center; gap:6px; padding:7px 14px; font-size:13px; cursor:pointer; border:1px solid #DDD9D0; background:#fff; color:#5C5752; }
.btn:disabled { opacity:.5; cursor:not-allowed; }
.btn-primary { background:#1D3557; color:#fff; border-color:#1D3557; }
.btn-sm { padding:5px 10px; font-size:12px; }
.btn-icon { width:28px; height:28px; border:1px solid #DDD9D0; background:#fff; cursor:pointer; font-size:12px; display:grid; place-items:center; }
.btn-icon.danger:hover { background:#FCF0EC; border-color:#E76F51; color:#E76F51; }

.modal-backdrop { position:fixed; inset:0; background:rgba(0,0,0,.35); z-index:100; display:grid; place-items:center; }
.modal { background:#fff; width:420px; max-width:95vw; border:1px solid #DDD9D0; display:flex; flex-direction:column; }
.modal-header { padding:16px 20px; border-bottom:1px solid #DDD9D0; display:flex; justify-content:space-between; align-items:center; font-size:14px; font-weight:600; }
.modal-body   { padding:20px; display:flex; flex-direction:column; gap:14px; }
.modal-footer { padding:16px 20px; border-top:1px solid #DDD9D0; display:flex; justify-content:flex-end; gap:8px; }
.form-group { display:flex; flex-direction:column; gap:6px; }
.label { font-size:12px; font-weight:500; color:#5C5752; }
.input { padding:8px 11px; border:1px solid #DDD9D0; background:#F7F6F2; font-size:13px; font-family:inherit; outline:none; }
.input:focus { border-color:#1D3557; background:#fff; }
.color-row { display:flex; gap:8px; flex-wrap:wrap; }
.color-dot { width:24px; height:24px; cursor:pointer; border:2px solid transparent; }
.color-dot.selected { outline:2px solid #1D3557; outline-offset:2px; }
.check { display:flex; align-items:center; gap:8px; font-size:13px; cursor:pointer; }
.form-error { font-size:12px; color:#E76F51; }
.backfill-progress { display:flex; flex-direction:column; gap:6px; }
.backfill-stage { font-size:12px; color:#5C5752; }
.progress-bar { height:6px; background:#F0EEE9; overflow:hidden; }
.progress-fill { height:100%; background:#1D3557; transition:width .2s ease; }
.backfill-truncated { margin-top:6px; font-size:12px; }
.field-hint { font-size:11px; color:#9A938C; }
.section-divider { font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.05em; color:#9A938C; border-top:1px solid #DDD9D0; padding-top:14px; margin-top:2px; }

.qr-box { display:flex; flex-direction:column; align-items:center; gap:8px; padding:14px; background:#F7F6F2; border:1px solid #DDD9D0; }
.qr-image { width:180px; height:180px; }
.token-list { display:flex; flex-direction:column; gap:8px; }
.token-row { display:flex; justify-content:space-between; align-items:center; padding:8px 10px; border:1px solid #DDD9D0; }
.token-label { font-size:13px; font-weight:600; }
.token-meta { font-size:11px; color:#9A938C; margin-top:2px; }
</style>
