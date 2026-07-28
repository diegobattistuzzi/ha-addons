<template>
  <div>
    <div class="topbar">
      <div class="topbar-title">{{ t('emailReceipts.title') }}</div>
    </div>

    <div class="content">
      <div v-if="loading" class="empty">{{ t('common.loading') }}</div>
      <div v-else-if="error" class="empty error-msg">{{ error }}</div>

      <template v-else>
        <div v-if="!emailReceipts.length" class="empty">
          {{ t('emailReceipts.empty') }}
        </div>
        <template v-else>
          <div class="info-box">
            {{ t('emailReceipts.infoBoxLine1') }}
            {{ t('emailReceipts.infoBoxLine2') }}
            <div class="rematch-row">
              <button class="btn btn-sm" @click="rematch" :disabled="rematching">
                {{ rematching ? t('emailReceipts.working') : t('emailReceipts.rematchButton') }}
              </button>
              <span v-if="rematchResult" class="rematch-result">{{ rematchResult }}</span>
            </div>
          </div>
          <table class="doc-table">
            <thead>
              <tr>
                <th>{{ t('emailReceipts.sender') }}</th>
                <th>{{ t('emailReceipts.subject') }}</th>
                <th>{{ t('common.amount') }}</th>
                <th>{{ t('common.date') }}</th>
                <th>{{ t('common.description') }}</th>
                <th>{{ t('emailReceipts.receivedAt') }}</th>
                <th>{{ t('emailReceipts.status') }}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in emailReceipts" :key="r.id" :ref="el => setRowRef(r.id, el)"
                :class="{ highlighted: r.id === highlightId }">
                <td class="doc-name">{{ r.merchant || r.sender }}</td>
                <td>{{ r.subject || '—' }}</td>
                <td class="num">{{ r.amount != null ? fmt(r.amount) : '—' }}</td>
                <td>{{ r.date || '—' }}</td>
                <td>{{ r.item_description || '—' }}</td>
                <td>{{ formatDate(r.received_at) }}</td>
                <td>
                  <span v-if="r.matched_transaction_id" class="doc-tag ok">{{ t('emailReceipts.matchedTag', { id: r.matched_transaction_id }) }}</span>
                  <span v-else class="doc-tag pending">{{ t('emailReceipts.pendingTag') }}</span>
                </td>
                <td>
                  <button v-if="r.matched_transaction_id" class="btn btn-sm"
                    :disabled="unmatchingId === r.id" @click="unmatch(r)">
                    {{ unmatchingId === r.id ? t('emailReceipts.working') : t('emailReceipts.unmatchButton') }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </template>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'

const route = useRoute()
const { t } = useI18n()

const emailReceipts = ref([])
const loading       = ref(true)
const error         = ref('')
const rematching    = ref(false)
const rematchResult = ref('')
const unmatchingId  = ref(null)
const highlightId   = ref(null)
const rowRefs       = new Map()

function setRowRef(id, el) {
  if (el) rowRefs.set(id, el)
  else rowRefs.delete(id)
}

const fmt = v => new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v)

function formatDate(value) {
  if (!value) return '—'
  return new Date(value.replace(' ', 'T') + 'Z').toLocaleString('it-IT')
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.get('api/email-receipts')
    emailReceipts.value = Array.isArray(res.data) ? res.data : []
  } catch (e) {
    error.value = e?.response?.data?.error || e.message || t('emailReceipts.errorLoading')
  } finally {
    loading.value = false
  }
}

// Se si arriva da "vai alla mail" di una transazione, la ricevuta puntata
// potrebbe non essere tra le ultime 100 mostrate di default: la recuperiamo
// per id (il backend la restituisce comunque, rispettando la visibilita') e la
// aggiungiamo in cima se manca, poi scrolliamo/evidenziamo quella riga.
async function applyHighlight() {
  const id = Number(route.query.highlight)
  highlightId.value = Number.isFinite(id) && id > 0 ? id : null
  if (!highlightId.value) return
  if (!emailReceipts.value.some(r => r.id === highlightId.value)) {
    try {
      const res = await api.get(`api/email-receipts?id=${highlightId.value}`)
      if (Array.isArray(res.data) && res.data.length) {
        emailReceipts.value = [res.data[0], ...emailReceipts.value]
      }
    } catch {
      // ricevuta non trovata o non visibile: resta comunque nell'elenco normale
    }
  }
  await nextTick()
  rowRefs.get(highlightId.value)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

async function rematch() {
  rematching.value = true
  rematchResult.value = ''
  try {
    const { data } = await api.post('api/email-receipts/rematch')
    rematchResult.value = data.matched
      ? t('emailReceipts.matchedCount', { count: data.matched })
      : t('emailReceipts.noNewMatch')
    await load()
  } catch (e) {
    rematchResult.value = e?.response?.data?.error || t('emailReceipts.errorRematch')
  } finally {
    rematching.value = false
  }
}

async function unmatch(receipt) {
  if (!confirm(t('emailReceipts.confirmUnmatch', { id: receipt.matched_transaction_id }))) return
  unmatchingId.value = receipt.id
  try {
    await api.post(`api/email-receipts/${receipt.id}/unmatch`)
    await load()
  } catch (e) {
    error.value = e?.response?.data?.error || t('emailReceipts.errorUnmatch')
  } finally {
    unmatchingId.value = null
  }
}

watch(() => route.query.highlight, applyHighlight)

onMounted(async () => {
  await load()
  await applyHighlight()
})
</script>

<style scoped>
.topbar { background:#fff; border-bottom:1px solid #DDD9D0; padding:0 28px; height:56px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10; }
.topbar-title { font-size:15px; font-weight:600; }

.content { padding:28px; max-width:1100px; }

.empty { text-align:center; padding:60px; color:#9A938C; font-size:13px; }
.error-msg { color:#E76F51; }

.info-box { padding:10px 14px; background:#EBF0F6; border:1px solid #1D3557; font-size:12px; color:#1D3557; line-height:1.6; margin-bottom:16px; }
.rematch-row { margin-top:8px; display:flex; align-items:center; gap:10px; }
.rematch-result { font-size:12px; }

.doc-table { width:100%; border-collapse:collapse; background:#fff; border:1px solid #DDD9D0; }
.doc-table th { text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:#9A938C; padding:10px 14px; border-bottom:1px solid #DDD9D0; }
.doc-table td { padding:10px 14px; font-size:13px; border-bottom:1px solid #EEEAE3; }
.doc-table td.num { font-variant-numeric:tabular-nums; }
.doc-table tr.highlighted { background:#FEF5E7; }
.doc-name { font-weight:500; }
.doc-tag { font-size:11px; color:#5C5752; white-space:nowrap; }
.doc-tag.ok { color:#2A9D8F; }
.doc-tag.pending { color:#E8A020; }

.btn { display:inline-flex; align-items:center; gap:6px; padding:6px 12px; font-size:12px; cursor:pointer; border:1px solid #DDD9D0; background:#fff; color:#5C5752; text-decoration:none; }
.btn-sm { padding:5px 10px; font-size:12px; }
</style>
