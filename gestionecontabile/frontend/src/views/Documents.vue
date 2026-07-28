<template>
  <div>
    <div class="topbar">
      <div class="topbar-title">{{ t('documents.title') }}</div>
      <div class="type-tabs">
        <button :class="['tab', tab==='coverage'  && 'active']" @click="tab='coverage'">{{ t('documents.tabs.coverage') }}</button>
        <button :class="['tab', tab==='documents' && 'active']" @click="tab='documents'">{{ t('documents.tabs.documents') }}</button>
      </div>
    </div>

    <div class="content">
      <div v-if="loading" class="empty">{{ t('documents.loading') }}</div>
      <div v-else-if="error" class="empty error-msg">{{ error }}</div>

      <template v-else-if="tab === 'coverage'">
        <div v-if="!coverageByAccount.length" class="empty">
          {{ t('documents.coverage.empty') }}
        </div>
        <template v-else>
          <div class="info-box">
            {{ t('documents.coverage.infoBox') }}
          </div>
          <div v-for="acc in coverageByAccount" :key="acc.accountId" class="coverage-account">
            <div class="coverage-account-header">
              <span class="coverage-account-name">{{ bankEmoji(acc.bank) }} {{ acc.accountName }}</span>
              <span class="coverage-account-range">{{ t('documents.coverage.coveredRange', { from: formatDay(acc.from), to: formatDay(acc.to) }) }}</span>
            </div>
            <table class="doc-table">
              <thead>
                <tr>
                  <th>{{ t('documents.coverage.table.file') }}</th>
                  <th>{{ t('documents.coverage.table.from') }}</th>
                  <th>{{ t('documents.coverage.table.to') }}</th>
                  <th>{{ t('documents.coverage.table.transactions') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in acc.rows" :key="row.key" :class="row.type === 'gap' && 'coverage-gap-row'">
                  <td v-if="row.type === 'gap'" colspan="4">{{ t('documents.coverage.gapWarning', { days: row.gapDays, unit: row.gapDays === 1 ? t('documents.coverage.dayUnit.singular') : t('documents.coverage.dayUnit.plural') }) }}</td>
                  <template v-else>
                    <td class="doc-name">{{ row.filename }}</td>
                    <td>{{ formatDay(row.period_start) }}</td>
                    <td>{{ formatDay(row.period_end) }}</td>
                    <td>{{ row.tx_count }}</td>
                  </template>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </template>

      <template v-else>
        <div v-if="!documents.length" class="empty">
          {{ t('documents.list.empty') }}
        </div>
        <table v-else class="doc-table">
          <thead>
            <tr>
              <th>{{ t('documents.list.table.file') }}</th>
              <th>{{ t('common.type') }}</th>
              <th>{{ t('documents.list.table.account') }}</th>
              <th>{{ t('documents.list.table.uploadedAt') }}</th>
              <th>{{ t('documents.list.table.size') }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in documents" :key="d.id">
              <td class="doc-name">{{ d.filename }}</td>
              <td>
                <span v-if="d.transaction_id" class="doc-tag">{{ t('documents.list.tag.attachedTransaction', { id: d.transaction_id }) }}</span>
                <span v-else-if="d.import_batch_id" class="doc-tag">{{ t('documents.list.tag.statement') }}</span>
                <span v-else class="muted">—</span>
              </td>
              <td>{{ accountName(d.account_id) }}</td>
              <td>{{ formatDate(d.uploaded_at) }}</td>
              <td>{{ formatSize(d.size_bytes) }}</td>
              <td class="doc-actions">
                <a :href="downloadUrl(d.id)" target="_blank" class="btn btn-sm">{{ t('documents.list.download') }}</a>
                <button class="btn-icon danger" @click="remove(d)" :title="t('documents.list.deleteTitle')">✕</button>
              </td>
            </tr>
          </tbody>
        </table>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'

const { t } = useI18n()

const documents = ref([])
const accounts  = ref([])
const loading   = ref(true)
const error     = ref('')
const tab       = ref('coverage')

// Solo gli estratti conto veri (import_batch_id, non un allegato singolo su
// una transazione) con almeno una transazione collegata: period_start/
// period_end/tx_count arrivano gia' calcolati da GET /api/documents (MIN/MAX
// delle date delle transazioni con quel document_id), non da un periodo
// dichiarato nel nome del file - riflettono cosa e' stato DAVVERO importato.
const coverageByAccount = computed(() => {
  const byAccount = new Map()
  for (const d of documents.value) {
    if (!d.import_batch_id || !d.period_start || !d.period_end) continue
    if (!byAccount.has(d.account_id)) byAccount.set(d.account_id, [])
    byAccount.get(d.account_id).push(d)
  }
  const result = []
  for (const [accountId, docs] of byAccount) {
    docs.sort((a, b) => a.period_start.localeCompare(b.period_start))
    // Righe gia' appiattite (l'eventuale avviso di buco e' una riga a se',
    // non un secondo elemento radice dentro lo stesso v-for): un v-for su un
    // <template> con piu' figli condizionali forza a mettere :key sul
    // <template> stesso, in conflitto con la regola eslint vue/no-v-for-
    // template-key - appiattendo qui evitiamo il problema alla radice invece
    // di doverlo sopprimere.
    const rows = []
    docs.forEach((d, i) => {
      if (i > 0) {
        const prevEnd = new Date(docs[i - 1].period_end + 'T00:00:00')
        const curStart = new Date(d.period_start + 'T00:00:00')
        const gapDays = Math.round((curStart - prevEnd) / 86400000) - 1
        if (gapDays > 0) rows.push({ type: 'gap', key: `gap-${d.id}`, gapDays })
      }
      rows.push({ type: 'doc', key: d.id, ...d })
    })
    const acc = accounts.value.find(a => a.id === accountId)
    result.push({
      accountId,
      accountName: acc ? acc.name : t('documents.list.accountFallback', { id: accountId }),
      bank: acc?.bank,
      from: docs[0].period_start,
      to: docs[docs.length - 1].period_end,
      rows,
    })
  }
  result.sort((a, b) => a.accountName.localeCompare(b.accountName))
  return result
})

const bankEmoji = b => ({ fineco:'🏦', ing:'🧡', n26:'🖤', revolut:'🌐', wise:'💚', hellobank:'💙', cash:'💵', other:'🏧' })[b] || '🏧'

function accountName(accountId) {
  const acc = accounts.value.find(a => a.id === accountId)
  return acc ? acc.name : (accountId ? t('documents.list.accountFallback', { id: accountId }) : '—')
}

function formatDate(value) {
  if (!value) return '—'
  return new Date(value.replace(' ', 'T') + 'Z').toLocaleString('it-IT')
}

function formatDay(value) {
  if (!value) return '—'
  return new Date(value + 'T00:00:00').toLocaleDateString('it-IT')
}

function formatSize(bytes) {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function downloadUrl(id) {
  return new URL(`api/documents/${id}/download`, document.baseURI).toString()
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [docsRes, accountsRes] = await Promise.all([
      api.get('api/documents'),
      api.get('api/accounts'),
    ])
    documents.value = docsRes.data
    accounts.value = accountsRes.data
  } catch (e) {
    error.value = e?.response?.data?.error || e.message || t('documents.error.loadFailed')
  } finally {
    loading.value = false
  }
}

async function remove(d) {
  if (!confirm(t('documents.confirmDelete', { filename: d.filename }))) return
  try {
    await api.delete(`api/documents/${d.id}`)
    load()
  } catch (e) {
    alert(e?.response?.data?.error || t('documents.error.deleteFailed'))
  }
}

onMounted(load)
</script>

<style scoped>
.topbar { background:#fff; border-bottom:1px solid #DDD9D0; padding:0 28px; height:56px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10; }
.topbar-title { font-size:15px; font-weight:600; }

.type-tabs { display:flex; gap:4px; }
.tab { padding:6px 14px; font-size:13px; border:none; background:none; cursor:pointer; color:#9A938C; border-radius:4px; }
.tab.active { background:#EEEAE3; color:#1D3557; font-weight:600; }

.content { padding:28px; max-width:1000px; }

.empty { text-align:center; padding:60px; color:#9A938C; font-size:13px; }
.error-msg { color:#E76F51; }

.info-box { padding:10px 14px; background:#EBF0F6; border:1px solid #1D3557; font-size:12px; color:#1D3557; line-height:1.6; margin-bottom:16px; }

.coverage-account { margin-bottom:24px; }
.coverage-account-header { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:6px; }
.coverage-account-name { font-size:14px; font-weight:600; color:#1D3557; }
.coverage-account-range { font-size:12px; color:#5C5752; }
.coverage-gap-row td { background:#FCF0EC; color:#E76F51; font-size:12px; font-weight:500; padding:6px 14px; }

.doc-table { width:100%; border-collapse:collapse; background:#fff; border:1px solid #DDD9D0; }
.doc-table th { text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:#9A938C; padding:10px 14px; border-bottom:1px solid #DDD9D0; }
.doc-table td { padding:10px 14px; font-size:13px; border-bottom:1px solid #EEEAE3; }
.doc-name { font-weight:500; }
.doc-tag { font-size:11px; color:#5C5752; white-space:nowrap; }
.muted { color:#DDD9D0; }
.doc-actions { display:flex; gap:8px; align-items:center; white-space:nowrap; }

.btn { display:inline-flex; align-items:center; gap:6px; padding:6px 12px; font-size:12px; cursor:pointer; border:1px solid #DDD9D0; background:#fff; color:#5C5752; text-decoration:none; }
.btn-sm { padding:5px 10px; font-size:12px; }
.btn-icon { width:26px; height:26px; border:1px solid #DDD9D0; background:#fff; cursor:pointer; font-size:12px; display:grid; place-items:center; }
.btn-icon.danger:hover { background:#FCF0EC; border-color:#E76F51; color:#E76F51; }
</style>
