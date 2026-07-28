<template>
  <div class="scan">
    <div class="topbar">
      <div class="topbar-title">{{ t('mobile.scan.title') }}</div>
      <div v-if="me" class="topbar-meta">{{ t('mobile.scan.greeting', { name: me.name }) }}</div>
    </div>

    <div class="content">
      <div v-if="!me && meError" class="empty error-msg">
        {{ meError }}
      </div>

      <template v-else>
        <label class="photo-drop" :class="{ busy: parsing }">
          <input type="file" accept="image/*" capture="environment" @change="onFileChange" :disabled="parsing" />
          <img v-if="previewUrl" :src="previewUrl" class="preview" />
          <span v-else class="photo-hint">{{ t('mobile.scan.takePhoto') }}</span>
        </label>

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
import { ref, computed, onMounted } from 'vue'
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

const form = ref({ amount: '', merchantName: '', date: '', categoryId: '', accountId: '', isCash: false })
const capturedFile = ref(null)
const showForm = computed(() => hasResult.value && !parsing.value)

async function loadContext() {
  try {
    const [meRes, accountsRes, categoriesRes] = await Promise.all([
      api.get('api/mobile/me'),
      api.get('api/accounts'),
      api.get('api/categories'),
    ])
    me.value = meRes.data
    accounts.value = accountsRes.data
    categories.value = categoriesRes.data.filter(c => c.is_active && c.type === 'expense')
  } catch (e) {
    meError.value = e?.response?.data?.detail || t('mobile.scan.contextError')
  }
}

function onAccountChange() {
  const acc = accounts.value.find(a => a.id === form.value.accountId)
  form.value.isCash = acc?.type === 'cash'
}

async function onFileChange(event) {
  const file = event.target.files?.[0]
  if (!file) return
  capturedFile.value = file
  previewUrl.value = URL.createObjectURL(file)
  hasResult.value = true
  savedOk.value = false
  saveError.value = ''
  parseError.value = ''
  voiceError.value = ''
  voiceTranscript.value = ''
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
      amount: form.value.amount,
      description: form.value.merchantName || t('mobile.scan.defaultDescription'),
      merchantName: form.value.merchantName,
      categoryId: form.value.categoryId || null,
      accountId: form.value.accountId,
      isCash: form.value.isCash,
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
    form.value = { amount: '', merchantName: '', date: '', categoryId: '', accountId: '', isCash: false }
  } catch (e) {
    saveError.value = e?.response?.data?.detail || t('mobile.scan.saveError')
  } finally {
    saving.value = false
  }
}

onMounted(loadContext)
</script>

<style scoped>
.scan { min-height: 100vh; background: #F7F5F1; }
.topbar { background:#fff; border-bottom:1px solid #DDD9D0; padding:14px 20px; position:sticky; top:0; z-index:10; }
.topbar-title { font-size:16px; font-weight:600; }
.topbar-meta { font-size:12px; color:#9A938C; margin-top:2px; }

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
