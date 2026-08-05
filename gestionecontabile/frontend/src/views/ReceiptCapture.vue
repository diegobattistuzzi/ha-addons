<template>
  <div class="scan">
    <div class="topbar">
      <div class="topbar-title">{{ t('mobile.scan.title') }}</div>
      <div v-if="me" class="topbar-meta">{{ t('mobile.scan.greeting', { name: me.name }) }}</div>
    </div>

    <div class="content">
      <div v-if="!me && meError" class="empty error-msg">
        {{ meError }}
        <button type="button" class="retry-btn" @click="loadContext()">{{ t('mobile.scan.retry') }}</button>
      </div>

      <template v-else>
        <div v-if="cropping" class="crop-stage">
          <div class="crop-wrap" ref="cropWrapRef">
            <img ref="cropImgRef" :src="rawPreviewUrl" class="crop-img" @load="onCropImageLoad" />
            <template v-if="cropReady">
              <svg class="crop-overlay" :viewBox="`0 0 ${cropWrapSize.w} ${cropWrapSize.h}`">
                <polygon :points="polygonPoints" class="crop-poly" />
              </svg>
              <div
                v-for="key in cornerKeys"
                :key="key"
                class="crop-handle"
                :style="{ left: displayCorners[key].x + 'px', top: displayCorners[key].y + 'px' }"
                @pointerdown="startDrag(key, $event)"
              ></div>
            </template>
          </div>
          <div class="hint">{{ t('mobile.scan.cropHint') }}</div>
          <div class="crop-actions">
            <button type="button" class="btn" @click="skipCrop">{{ t('mobile.scan.cropSkip') }}</button>
            <button type="button" class="btn btn-primary" @click="confirmCrop" :disabled="!cropReady">{{ t('mobile.scan.cropConfirm') }}</button>
          </div>
        </div>

        <label v-else class="photo-drop" :class="{ busy: parsing }">
          <input type="file" accept="image/*" capture="environment" @change="onFileChange" :disabled="parsing" />
          <img v-if="previewUrl" :src="previewUrl" class="preview" />
          <span v-else class="photo-hint">{{ t('mobile.scan.takePhoto') }}</span>
        </label>

        <template v-if="!cropping">
          <div class="or-divider">{{ t('mobile.scan.or') }}</div>

          <button type="button" class="voice-btn" :class="{ listening }" :disabled="parsing || !voiceSupported" @click="toggleVoice">
            <span class="voice-icon">{{ listening ? '⏹️' : '🎤' }}</span>
            {{ listening ? t('mobile.scan.voiceListening') : t('mobile.scan.voiceButton') }}
          </button>
          <div v-if="!voiceSupported" class="hint">{{ t('mobile.scan.voiceNotSupported') }}</div>
          <div v-else-if="voiceTranscript" class="hint">"{{ voiceTranscript }}"</div>
          <div v-if="voiceError" class="empty error-msg">{{ voiceError }}</div>

          <div v-if="parsing" class="hint">{{ t('mobile.scan.analyzing') }}</div>
          <div v-if="parseError" class="empty error-msg">{{ parseError }}</div>

          <button v-if="!showForm" type="button" class="manual-link" @click="startManualEntry">
            {{ t('mobile.scan.manualEntry') }}
          </button>
        </template>

        <form v-if="showForm" class="form" @submit.prevent="save">
          <div class="form-group">
            <label class="label">{{ t('mobile.scan.amountLabel') }}</label>
            <input class="input" type="number" step="0.01" v-model="form.amount" required />
          </div>
          <div class="form-group">
            <label class="label">{{ t('mobile.scan.merchantLabel') }}</label>
            <input class="input" v-model="form.merchantName" />
          </div>
          <div class="form-group">
            <label class="label">{{ t('mobile.scan.dateLabel') }}</label>
            <input class="input" type="date" v-model="form.date" required />
          </div>
          <div class="form-group">
            <label class="label">{{ t('mobile.scan.categoryLabel') }}</label>
            <select class="input" v-model="form.categoryId">
              <option value="">{{ t('mobile.scan.categoryNone') }}</option>
              <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.icon }} {{ c.name }}</option>
            </select>
          </div>
          <div class="form-group">
            <label class="label">{{ t('mobile.scan.accountLabel') }}</label>
            <select class="input" v-model="form.accountId" required @change="onAccountChange">
              <option value="" disabled>{{ t('mobile.scan.accountPlaceholder') }}</option>
              <option v-for="a in accounts" :key="a.id" :value="a.id">
                {{ a.type === 'cash' ? '💵 ' : '' }}{{ a.name }}
              </option>
            </select>
          </div>
          <div class="form-group">
            <label class="label">{{ t('mobile.scan.destinationLabel') }}</label>
            <select class="input" v-model="form.destination">
              <option value="family">{{ t('transactions.destination.family') }}</option>
              <option value="personal">{{ t('transactions.destination.personal') }}</option>
            </select>
          </div>

          <div v-if="saveError" class="empty error-msg">{{ saveError }}</div>

          <button class="btn btn-primary btn-block" type="submit" :disabled="saving">
            {{ saving ? t('mobile.scan.saving') : t('mobile.scan.save') }}
          </button>
        </form>

        <div v-if="savedOk" class="empty success-msg">{{ t('mobile.scan.saved') }}</div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'

const { t, locale } = useI18n()

const me = ref(null)
const meError = ref('')
const accounts = ref([])
const categories = ref([])

const previewUrl = ref('')
const hasResult = ref(false)
const parsing = ref(false)
const parseError = ref('')
const saving = ref(false)
const saveError = ref('')
const savedOk = ref(false)

const listening = ref(false)
const voiceTranscript = ref('')
const voiceError = ref('')
const SpeechRecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition
const voiceSupported = !!SpeechRecognitionImpl
let recognition = null

const form = ref({ amount: '', merchantName: '', date: '', categoryId: '', accountId: '', isCash: false, destination: 'family' })
const capturedFile = ref(null)
const showForm = computed(() => hasResult.value && !parsing.value)

// Ritaglio scontrino: rilevamento bordi + prospettiva via jscanify/OpenCV.js,
// caricati pigramente (sono pesanti, ~8MB) solo quando serve, cosi' non
// appesantiscono il caricamento iniziale della PWA. Se il rilevamento fallisce
// o le librerie non si caricano (rete instabile), l'utente puo' comunque
// procedere con "Usa foto originale": il ritaglio e' solo un miglioramento
// estetico dell'allegato, non deve mai bloccare il flusso di inserimento spesa.
const cropping = ref(false)
const cropReady = ref(false)
const rawPreviewUrl = ref('')
const cropImgRef = ref(null)
const cropWrapRef = ref(null)
const cropWrapSize = ref({ w: 0, h: 0 })
const displayScale = ref(1)
const cornerKeys = ['topLeftCorner', 'topRightCorner', 'bottomLeftCorner', 'bottomRightCorner']
const cropNatural = ref(null)
const draggingCorner = ref(null)
let scannerPromise = null

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const el = document.createElement('script')
    el.src = src
    el.onload = resolve
    el.onerror = () => reject(new Error(`load failed: ${src}`))
    document.head.appendChild(el)
  })
}

function ensureScanner() {
  if (!scannerPromise) {
    scannerPromise = (async () => {
      const base = import.meta.env.BASE_URL
      await loadScript(`${base}vendor/opencv.js`)
      await new Promise(resolve => {
        if (window.cv?.Mat) return resolve()
        window.cv['onRuntimeInitialized'] = resolve
      })
      await loadScript(`${base}vendor/jscanify.js`)
      return new window.jscanify()
    })()
  }
  return scannerPromise
}

function distance(p1, p2) {
  return Math.hypot(p1.x - p2.x, p1.y - p2.y)
}

function defaultCorners(w, h) {
  const m = 0.05
  return {
    topLeftCorner: { x: w * m, y: h * m },
    topRightCorner: { x: w * (1 - m), y: h * m },
    bottomLeftCorner: { x: w * m, y: h * (1 - m) },
    bottomRightCorner: { x: w * (1 - m), y: h * (1 - m) },
  }
}

const displayCorners = computed(() => {
  const scale = displayScale.value
  const c = cropNatural.value || defaultCorners(0, 0)
  const out = {}
  for (const key of cornerKeys) out[key] = { x: c[key].x * scale, y: c[key].y * scale }
  return out
})

const polygonPoints = computed(() => {
  const c = displayCorners.value
  return ['topLeftCorner', 'topRightCorner', 'bottomRightCorner', 'bottomLeftCorner']
    .map(key => `${c[key].x},${c[key].y}`)
    .join(' ')
})

async function onCropImageLoad() {
  const imgEl = cropImgRef.value
  if (!imgEl) return
  const naturalW = imgEl.naturalWidth
  const naturalH = imgEl.naturalHeight
  cropWrapSize.value = { w: imgEl.clientWidth, h: imgEl.clientHeight }
  displayScale.value = imgEl.clientWidth / naturalW
  cropNatural.value = defaultCorners(naturalW, naturalH)

  try {
    const scanner = await ensureScanner()
    const img = window.cv.imread(imgEl)
    const contour = scanner.findPaperContour(img)
    if (contour) {
      const corners = scanner.getCornerPoints(contour)
      contour.delete()
      if (corners.topLeftCorner && corners.topRightCorner && corners.bottomLeftCorner && corners.bottomRightCorner) {
        cropNatural.value = corners
      }
    }
    img.delete()
  } catch {
    // Niente rilevamento automatico: restano gli angoli di default, l'utente li aggiusta a mano.
  }
  cropReady.value = true
}

function startDrag(key, event) {
  event.preventDefault()
  draggingCorner.value = key
  window.addEventListener('pointermove', onDrag)
  window.addEventListener('pointerup', stopDrag)
}

function onDrag(event) {
  if (!draggingCorner.value || !cropWrapRef.value) return
  const rect = cropWrapRef.value.getBoundingClientRect()
  const x = Math.min(Math.max(event.clientX - rect.left, 0), rect.width)
  const y = Math.min(Math.max(event.clientY - rect.top, 0), rect.height)
  const scale = displayScale.value || 1
  cropNatural.value = { ...cropNatural.value, [draggingCorner.value]: { x: x / scale, y: y / scale } }
}

function stopDrag() {
  draggingCorner.value = null
  window.removeEventListener('pointermove', onDrag)
  window.removeEventListener('pointerup', stopDrag)
}

async function confirmCrop() {
  const imgEl = cropImgRef.value
  const corners = cropNatural.value
  try {
    const scanner = await ensureScanner()
    const widthTop = distance(corners.topLeftCorner, corners.topRightCorner)
    const widthBottom = distance(corners.bottomLeftCorner, corners.bottomRightCorner)
    const heightLeft = distance(corners.topLeftCorner, corners.bottomLeftCorner)
    const heightRight = distance(corners.topRightCorner, corners.bottomRightCorner)
    const outW = Math.round(Math.max(widthTop, widthBottom))
    const outH = Math.round(Math.max(heightLeft, heightRight))
    const canvas = scanner.extractPaper(imgEl, outW, outH, corners)
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.92))
    const croppedFile = new File([blob], 'scontrino.jpg', { type: 'image/jpeg' })
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = URL.createObjectURL(blob)
    capturedFile.value = croppedFile
    finishCropStage()
    await analyzeReceipt(croppedFile)
  } catch {
    // Estrazione fallita: si prosegue con la foto originale, il ritaglio resta solo un miglioramento facoltativo.
    await skipCrop()
  }
}

async function skipCrop() {
  previewUrl.value = rawPreviewUrl.value
  rawPreviewUrl.value = ''
  cropping.value = false
  cropReady.value = false
  cropNatural.value = null
  await analyzeReceipt(capturedFile.value)
}

function finishCropStage() {
  cropping.value = false
  cropReady.value = false
  cropNatural.value = null
  URL.revokeObjectURL(rawPreviewUrl.value)
  rawPreviewUrl.value = ''
}

// Un 401 vero (token invalido/revocato) e' l'unico caso in cui ha senso dire
// all'utente "il link e' scaduto/revocato": qualunque altro errore (rete
// instabile al risveglio del telefono, backend che si sta ancora avviando,
// timeout) e' transitorio e sparisce da solo - riprovare in automatico un
// paio di volte evita di allarmare l'utente e di richiedere un refresh
// manuale per un problema che si risolve da solo in un secondo.
async function loadContext(attempt = 1) {
  meError.value = ''
  try {
    const [meRes, accountsRes, categoriesRes] = await Promise.all([
      api.get('api/mobile/me'),
      api.get('api/accounts'),
      api.get('api/categories'),
    ])
    me.value = meRes.data
    accounts.value = accountsRes.data
    categories.value = categoriesRes.data
      .filter(c => c.is_active && c.type === 'expense')
      .sort((a, b) => a.name.localeCompare(b.name))
  } catch (e) {
    const isAuthError = e?.response?.status === 401
    if (!isAuthError && attempt < 3) {
      await new Promise(r => setTimeout(r, attempt * 800))
      return loadContext(attempt + 1)
    }
    meError.value = isAuthError
      ? (e?.response?.data?.detail || t('mobile.scan.contextError'))
      : t('mobile.scan.connectionError')
  }
}

// Foto e dettatura sono scorciatoie per precompilare il form, non l'unico modo
// per inserire una spesa: senza questo, chi non puo'/non vuole parlare o
// scattare una foto (rumore ambientale, mani occupate, scontrino illeggibile)
// non avrebbe alternative per registrare la spesa dal cellulare.
function startManualEntry() {
  previewUrl.value = ''
  capturedFile.value = null
  voiceTranscript.value = ''
  parseError.value = ''
  savedOk.value = false
  form.value = { amount: '', merchantName: '', date: new Date().toISOString().slice(0, 10), categoryId: '', accountId: '', isCash: false, destination: 'family' }
  hasResult.value = true
}

function onAccountChange() {
  const acc = accounts.value.find(a => a.id === form.value.accountId)
  form.value.isCash = acc?.type === 'cash'
}

function onFileChange(event) {
  const file = event.target.files?.[0]
  if (!file) return
  capturedFile.value = file
  rawPreviewUrl.value = URL.createObjectURL(file)
  savedOk.value = false
  saveError.value = ''
  parseError.value = ''
  voiceError.value = ''
  voiceTranscript.value = ''
  cropReady.value = false
  cropping.value = true
}

async function analyzeReceipt(file) {
  hasResult.value = true
  parsing.value = true
  try {
    const body = new FormData()
    body.append('file', file)
    const { data } = await api.post('api/transactions/ai-parse-receipt', body)
    form.value.amount = data.amount ?? ''
    form.value.merchantName = data.merchantName ?? ''
    form.value.date = data.date || new Date().toISOString().slice(0, 10)
    form.value.categoryId = data.categoryId ?? ''
  } catch (e) {
    parseError.value = e?.response?.data?.detail || t('mobile.scan.parseError')
    form.value.date = new Date().toISOString().slice(0, 10)
  } finally {
    parsing.value = false
  }
}

function toggleVoice() {
  if (listening.value) {
    recognition?.stop()
    return
  }
  voiceError.value = ''
  voiceTranscript.value = ''
  parseError.value = ''
  recognition = new SpeechRecognitionImpl()
  recognition.lang = locale.value === 'it' ? 'it-IT' : 'en-US'
  recognition.interimResults = false
  recognition.maxAlternatives = 1

  recognition.onresult = event => {
    const text = event.results[0][0].transcript
    voiceTranscript.value = text
    parseVoiceText(text)
  }
  recognition.onerror = event => {
    listening.value = false
    voiceError.value = event.error === 'no-speech'
      ? t('mobile.scan.voiceNoSpeech')
      : t('mobile.scan.voiceError')
  }
  recognition.onend = () => { listening.value = false }

  listening.value = true
  recognition.start()
}

async function parseVoiceText(text) {
  previewUrl.value = ''
  capturedFile.value = null
  hasResult.value = true
  savedOk.value = false
  saveError.value = ''
  parseError.value = ''
  parsing.value = true
  try {
    const { data } = await api.post('api/transactions/ai-parse', { text })
    form.value.amount = data.amount ?? ''
    form.value.merchantName = data.description ?? ''
    form.value.date = data.date || new Date().toISOString().slice(0, 10)
    form.value.categoryId = data.categoryId ?? ''
    if (data.accountId) {
      form.value.accountId = data.accountId
      onAccountChange()
    }
  } catch (e) {
    parseError.value = e?.response?.data?.detail || t('mobile.scan.parseError')
    form.value.date = new Date().toISOString().slice(0, 10)
  } finally {
    parsing.value = false
  }
}

async function save() {
  saving.value = true
  saveError.value = ''
  try {
    const { data: created } = await api.post('api/transactions', {
      date: form.value.date,
      amount: -Math.abs(Number(form.value.amount)),
      description: form.value.merchantName || t('mobile.scan.defaultDescription'),
      merchantName: form.value.merchantName,
      categoryId: form.value.categoryId || null,
      accountId: form.value.accountId,
      isCash: form.value.isCash,
      destination: form.value.destination,
      paidByPersonId: me.value?.id,
    })
    // La foto dello scontrino e' servita finora solo per farla leggere all'AI:
    // la alleghiamo ora alla transazione appena creata, cosi' resta consultabile
    // in seguito (Documenti / dettaglio transazione) invece di andare persa.
    if (capturedFile.value) {
      try {
        const body = new FormData()
        body.append('file', capturedFile.value)
        await api.post(`api/transactions/${created.id}/documents`, body)
      } catch {
        // La transazione e' comunque salvata: l'allegato e' un di piu', non blocca il flusso.
      }
    }
    savedOk.value = true
    previewUrl.value = ''
    capturedFile.value = null
    hasResult.value = false
    voiceTranscript.value = ''
    form.value = { amount: '', merchantName: '', date: '', categoryId: '', accountId: '', isCash: false, destination: 'family' }
  } catch (e) {
    saveError.value = e?.response?.data?.detail || t('mobile.scan.saveError')
  } finally {
    saving.value = false
  }
}

onMounted(loadContext)
onBeforeUnmount(stopDrag)
</script>

<style scoped>
.scan { min-height: 100vh; background: #F7F5F1; }
.topbar { background:#fff; border-bottom:1px solid #DDD9D0; padding:14px 20px; position:sticky; top:0; z-index:10; }
.topbar-title { font-size:16px; font-weight:600; }
.topbar-meta { font-size:12px; color:#9A938C; margin-top:2px; }

.crop-stage { display:flex; flex-direction:column; gap:8px; }
.crop-wrap { position:relative; width:100%; user-select:none; -webkit-user-select:none; touch-action:none; }
.crop-img { width:100%; height:auto; display:block; border-radius:6px; }
.crop-overlay { position:absolute; inset:0; width:100%; height:100%; pointer-events:none; }
.crop-poly { fill:rgba(29,53,87,0.25); stroke:#1D3557; stroke-width:3; }
.crop-handle {
  position:absolute; width:28px; height:28px; margin-left:-14px; margin-top:-14px;
  border-radius:50%; background:#1D3557; border:3px solid #fff; box-shadow:0 1px 4px rgba(0,0,0,0.4);
  cursor:grab; touch-action:none;
}
.crop-actions { display:flex; gap:10px; margin-top:6px; }
.crop-actions .btn { flex:1; }

.content { padding:20px; max-width:480px; margin:0 auto; }

.photo-drop { display:block; border:2px dashed #DDD9D0; border-radius:8px; padding:32px 16px; text-align:center; cursor:pointer; background:#fff; position:relative; }
.photo-drop.busy { opacity:0.6; pointer-events:none; }
.photo-drop input { position:absolute; inset:0; opacity:0; cursor:pointer; }
.photo-hint { color:#9A938C; font-size:14px; }
.preview { max-width:100%; max-height:280px; border-radius:6px; }

.or-divider { text-align:center; color:#9A938C; font-size:11px; text-transform:uppercase; letter-spacing:.08em; margin:14px 0; }

.voice-btn { width:100%; display:flex; align-items:center; justify-content:center; gap:8px; padding:14px; font-size:14px; font-weight:600; cursor:pointer; border:2px solid #1D3557; border-radius:8px; background:#fff; color:#1D3557; }
.voice-btn.listening { background:#E76F51; border-color:#E76F51; color:#fff; animation: pulse 1.4s ease-in-out infinite; }
.voice-btn:disabled { opacity:0.5; cursor:default; }
.voice-icon { font-size:18px; }
@keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:.6; } }

.hint { text-align:center; color:#9A938C; font-size:13px; margin-top:10px; }
.manual-link { display:block; width:100%; text-align:center; background:none; border:none; color:#1D3557; font-size:13px; text-decoration:underline; cursor:pointer; padding:14px 0 4px; }
.retry-btn { display:block; margin:10px auto 0; padding:8px 18px; font-size:13px; font-weight:600; cursor:pointer; border:1px solid #E76F51; border-radius:6px; background:#fff; color:#E76F51; }
.empty { text-align:center; padding:16px; font-size:13px; }
.error-msg { color:#E76F51; }
.success-msg { color:#2A9D8F; font-weight:600; }

.form { margin-top:20px; display:flex; flex-direction:column; gap:14px; }
.form-group { display:flex; flex-direction:column; gap:4px; }
.label { font-size:12px; color:#5C5752; font-weight:600; }
.input { padding:10px 12px; font-size:15px; border:1px solid #DDD9D0; border-radius:6px; }

.btn { display:inline-flex; align-items:center; justify-content:center; gap:6px; padding:8px 14px; font-size:14px; cursor:pointer; border:1px solid #DDD9D0; background:#fff; color:#5C5752; }
.btn-primary { background:#1D3557; border-color:#1D3557; color:#fff; }
.btn-block { width:100%; padding:14px; font-size:15px; font-weight:600; }
.btn:disabled { opacity:0.6; cursor:default; }
</style>
