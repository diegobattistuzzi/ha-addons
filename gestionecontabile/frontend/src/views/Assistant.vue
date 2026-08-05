<template>
  <div>
    <div class="topbar">
      <div class="topbar-title">{{ t('assistant.title') }}</div>
    </div>
    <div class="content">
      <div class="tab-row">
        <button class="tab-btn" :class="{ active: mode === 'summary' }" @click="mode = 'summary'">{{ t('assistant.tabs.summary') }}</button>
        <button class="tab-btn" :class="{ active: mode === 'chat' }" @click="mode = 'chat'">{{ t('assistant.tabs.chat') }}</button>
      </div>

      <template v-if="mode === 'summary'">
        <div class="period-row">
          <input class="input period-picker" type="month" v-model="period" />
          <select class="input period-picker" v-model="accountId">
            <option value="">{{ t('reports.allAccounts') }}</option>
            <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select>
        </div>

        <div class="card" style="margin-bottom:16px">
          <div class="card-title-row">
            <div class="card-title">{{ t('assistant.summary.title') }}</div>
            <button class="btn btn-sm" :disabled="summaryLoading" @click="loadSummary">
              {{ summaryLoading ? t('assistant.summary.generating') : t('assistant.summary.generate') }}
            </button>
          </div>
          <div v-if="summaryError" class="empty error-msg">{{ summaryError }}</div>
          <div v-else-if="summaryHtml" class="markdown" v-html="summaryHtml"></div>
          <div v-else class="empty">{{ t('assistant.summary.empty') }}</div>
        </div>

        <div class="card">
          <div class="card-title-row">
            <div class="card-title">{{ t('assistant.anomalies.title') }}</div>
            <button class="btn btn-sm" :disabled="anomaliesLoading" @click="loadAnomalies">
              {{ anomaliesLoading ? t('assistant.summary.generating') : t('assistant.summary.generate') }}
            </button>
          </div>
          <div v-if="anomaliesError" class="empty error-msg">{{ anomaliesError }}</div>
          <div v-else-if="anomalies.length" class="anomaly-list">
            <div v-for="(a, i) in anomalies" :key="i" class="anomaly-row" :class="'sev-' + a.severity">
              <span class="anomaly-message">{{ a.message || anomalyFallback(a) }}</span>
            </div>
          </div>
          <div v-else-if="anomaliesChecked" class="empty">{{ t('assistant.anomalies.none') }}</div>
          <div v-else class="empty">{{ t('assistant.anomalies.empty') }}</div>
        </div>
      </template>

      <template v-else>
        <div class="chat-layout">
          <div class="chat-sidebar">
            <button class="btn btn-sm" style="width:100%;margin-bottom:8px" @click="newConversation">+ {{ t('assistant.chat.newConversation') }}</button>
            <div v-if="!conversations.length" class="empty" style="padding:16px">{{ t('assistant.chat.noConversations') }}</div>
            <div v-for="c in conversations" :key="c.id" class="conversation-row" :class="{ active: c.id === conversationId }">
              <span class="conversation-title" @click="openConversation(c.id)">{{ c.title }}</span>
              <button class="btn-icon danger" @click="deleteConversation(c.id)" :title="t('common.delete')">✕</button>
            </div>
          </div>

          <div class="chat-main">
            <div class="chat-messages" ref="messagesEl">
              <div v-if="!messages.length" class="empty" style="padding:40px">{{ t('assistant.chat.empty') }}</div>
              <div v-for="(m, i) in messages" :key="i" class="bubble-row" :class="m.role">
                <div class="bubble" :class="m.role">
                  <div v-if="m.role === 'assistant'" class="markdown" v-html="renderMarkdown(m.content)"></div>
                  <div v-else>{{ m.content }}</div>
                </div>
              </div>
              <div v-if="chatLoading" class="bubble-row assistant">
                <div class="bubble assistant">{{ t('assistant.chat.thinking') }}</div>
              </div>
            </div>

            <div v-if="lastQueryConfig" class="card" style="margin:0 0 12px">
              <div class="card-title-row">
                <div class="card-title">{{ t('assistant.chat.chartPreview') }}</div>
                <button class="btn btn-sm" @click="saveLastAsReport">💾 {{ t('assistant.chat.saveAsReport') }}</button>
              </div>
              <SimpleBarChart :rows="lastQueryRows" />
            </div>

            <form class="chat-input-row" @submit.prevent="send">
              <input class="input" style="flex:1" v-model="draft" :placeholder="t('assistant.chat.placeholder')" :disabled="chatLoading" />
              <button class="btn btn-primary" type="submit" :disabled="chatLoading || !draft.trim()">{{ t('assistant.chat.send') }}</button>
            </form>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { api } from '../api.js'
import SimpleBarChart from '../components/SimpleBarChart.vue'

const { t } = useI18n()

const mode = ref('summary')
const period = ref(new Date().toISOString().slice(0, 7))
const accountId = ref('')
const accounts = ref([])

const summaryHtml = ref('')
const summaryLoading = ref(false)
const summaryError = ref('')

const anomalies = ref([])
const anomaliesChecked = ref(false)
const anomaliesLoading = ref(false)
const anomaliesError = ref('')

function renderMarkdown(text) {
  return DOMPurify.sanitize(marked.parse(text || ''))
}

function anomalyFallback(a) {
  if (a.type === 'category_spike') return t('assistant.anomalies.categorySpike', { category: a.category })
  if (a.type === 'new_merchant') return t('assistant.anomalies.newMerchant', { merchant: a.merchant })
  return ''
}

async function loadSummary() {
  summaryLoading.value = true
  summaryError.value = ''
  try {
    const res = await api.post('api/ai/summary', { month: period.value, accountId: accountId.value || undefined })
    summaryHtml.value = renderMarkdown(res.data.text)
  } catch (e) {
    summaryError.value = e?.response?.data?.detail || t('assistant.errors.generic')
  } finally {
    summaryLoading.value = false
  }
}

async function loadAnomalies() {
  anomaliesLoading.value = true
  anomaliesError.value = ''
  try {
    const res = await api.post('api/ai/anomalies', { month: period.value, accountId: accountId.value || undefined })
    anomalies.value = res.data.anomalies || []
    anomaliesChecked.value = true
  } catch (e) {
    anomaliesError.value = e?.response?.data?.detail || t('assistant.errors.generic')
  } finally {
    anomaliesLoading.value = false
  }
}

async function loadAccounts() {
  const res = await api.get('api/accounts')
  accounts.value = Array.isArray(res.data) ? res.data : []
}

// Chat
const conversations = ref([])
const conversationId = ref(null)
const messages = ref([])
const draft = ref('')
const chatLoading = ref(false)
const messagesEl = ref(null)
const lastQueryConfig = ref(null)
const lastQueryRows = ref([])

async function loadConversations() {
  const res = await api.get('api/ai/conversations')
  conversations.value = Array.isArray(res.data) ? res.data : []
}

async function openConversation(id) {
  conversationId.value = id
  lastQueryConfig.value = null
  lastQueryRows.value = []
  const res = await api.get(`api/ai/conversations/${id}/messages`)
  messages.value = (res.data || []).map(m => ({ role: m.role, content: m.content }))
  const last = (res.data || []).slice().reverse().find(m => m.queryConfig)
  if (last) {
    lastQueryConfig.value = last.queryConfig
    await loadLastQueryRows()
  }
  scrollToBottom()
}

function newConversation() {
  conversationId.value = null
  messages.value = []
  lastQueryConfig.value = null
  lastQueryRows.value = []
}

async function deleteConversation(id) {
  if (!confirm(t('assistant.chat.confirmDelete'))) return
  await api.delete(`api/ai/conversations/${id}`)
  conversations.value = conversations.value.filter(c => c.id !== id)
  if (conversationId.value === id) newConversation()
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  })
}

async function loadLastQueryRows() {
  if (!lastQueryConfig.value) return
  try {
    const res = await api.post('api/reports/query', lastQueryConfig.value)
    lastQueryRows.value = (Array.isArray(res.data) ? res.data : []).map(r => ({ label: r.dim0, value: r.value }))
  } catch (e) {
    lastQueryRows.value = []
  }
}

async function send() {
  const message = draft.value.trim()
  if (!message) return
  messages.value.push({ role: 'user', content: message })
  draft.value = ''
  chatLoading.value = true
  scrollToBottom()
  try {
    const res = await api.post('api/ai/chat', {
      conversationId: conversationId.value || undefined,
      message,
      month: period.value,
    })
    conversationId.value = res.data.conversationId
    messages.value.push({ role: 'assistant', content: res.data.reply })
    lastQueryConfig.value = res.data.queryConfig || null
    if (lastQueryConfig.value) await loadLastQueryRows()
    else lastQueryRows.value = []
    await loadConversations()
  } catch (e) {
    messages.value.push({ role: 'assistant', content: e?.response?.data?.detail || t('assistant.errors.generic') })
  } finally {
    chatLoading.value = false
    scrollToBottom()
  }
}

async function saveLastAsReport() {
  if (!lastQueryConfig.value) return
  const name = prompt(t('reportBuilder.prompts.reportName'))
  if (!name) return
  await api.post('api/reports/custom', { name, config: lastQueryConfig.value })
  alert(t('assistant.chat.savedConfirmation'))
}

watch(period, () => {
  summaryHtml.value = ''
  anomalies.value = []
  anomaliesChecked.value = false
})

onMounted(() => {
  loadAccounts()
  loadConversations()
})
</script>

<style scoped>
.topbar { background:#fff; border-bottom:1px solid #DDD9D0; padding:0 28px; height:56px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10; }
.topbar-title { font-size:15px; font-weight:600; }
.content { padding:28px; }
.tab-row { display:flex; gap:8px; margin-bottom:20px; }
.tab-btn { padding:8px 18px; border:1px solid #DDD9D0; font-size:12.5px; cursor:pointer; background:#fff; color:#5C5752; }
.tab-btn.active { background:#1D3557; color:#fff; border-color:#1D3557; }
.period-row { display:flex; align-items:center; gap:8px; margin-bottom:24px; flex-wrap:wrap; }
.input { padding:8px 11px; border:1px solid #DDD9D0; background:#F7F6F2; font-size:13px; font-family:inherit; outline:none; }
.input:focus { border-color:#1D3557; background:#fff; }
.period-picker { margin-right:8px; }
.card { background:#fff; border:1px solid #DDD9D0; padding:20px; }
.card-title-row { display:flex; align-items:center; justify-content:space-between; margin-bottom:16px; }
.card-title { font-size:13px; font-weight:600; }
.btn { display:inline-flex; align-items:center; padding:7px 14px; font-size:13px; cursor:pointer; border:1px solid #DDD9D0; background:#fff; color:#5C5752; }
.btn-primary { background:#1D3557; color:#fff; border-color:#1D3557; }
.btn-sm { padding:5px 10px; font-size:12px; }
.btn:disabled { opacity:.5; cursor:default; }
.btn-icon { border:1px solid #DDD9D0; background:#fff; width:26px; height:26px; display:inline-flex; align-items:center; justify-content:center; cursor:pointer; color:#5C5752; }
.btn-icon.danger:hover { color:#E76F51; border-color:#E76F51; }
.empty { text-align:center; padding:24px; color:#9A938C; font-size:13px; }
.error-msg { color:#E76F51; }
.markdown :deep(p) { margin:0 0 8px; font-size:13px; line-height:1.6; }
.markdown :deep(ul) { margin:0 0 8px 18px; font-size:13px; }
.markdown :deep(strong) { color:#1D3557; }

.anomaly-list { display:flex; flex-direction:column; gap:8px; }
.anomaly-row { padding:10px 12px; font-size:12.5px; border-left:3px solid #DDD9D0; background:#F7F6F2; }
.anomaly-row.sev-high { border-color:#E76F51; background:#FCF0EC; }
.anomaly-row.sev-medium { border-color:#E8A020; background:#FBF3E6; }
.anomaly-row.sev-low { border-color:#9A938C; }

.chat-layout { display:grid; grid-template-columns:240px 1fr; gap:16px; height:calc(100vh - 180px); }
.chat-sidebar { background:#fff; border:1px solid #DDD9D0; padding:12px; overflow-y:auto; }
.conversation-row { display:flex; align-items:center; justify-content:space-between; gap:6px; padding:8px; font-size:12.5px; cursor:pointer; }
.conversation-row:hover, .conversation-row.active { background:#F0EEE9; }
.conversation-title { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.chat-main { display:flex; flex-direction:column; gap:12px; min-height:0; }
.chat-messages { flex:1; overflow-y:auto; background:#fff; border:1px solid #DDD9D0; padding:16px; display:flex; flex-direction:column; gap:10px; }
.bubble-row { display:flex; }
.bubble-row.user { justify-content:flex-end; }
.bubble { max-width:75%; padding:10px 14px; font-size:13px; border-radius:2px; }
.bubble.user { background:#1D3557; color:#fff; }
.bubble.assistant { background:#F0EEE9; color:#333; }
.chat-input-row { display:flex; gap:8px; }
</style>
