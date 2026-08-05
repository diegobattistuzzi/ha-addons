<template>
  <div>
    <div class="topbar">
      <div class="topbar-title">{{ t('setup.topbarTitle') }}</div>
      <div class="topbar-actions">
        <span v-if="saved" class="saved-badge">✓ {{ t('setup.saved') }}</span>
        <span v-if="error" class="error-badge">✗ {{ error }}</span>
      </div>
    </div>

    <div class="content">

      <!-- Connessione backend -->
      <div class="status-bar" :class="backendOk ? 'ok' : 'fail'">
        <span>{{ backendOk ? ('✓ ' + t('setup.backend.ok')) : ('✗ ' + t('setup.backend.fail')) }}</span>
        <span v-if="backendOk" class="status-detail">{{ apiBase }}</span>
      </div>

      <!-- BUDGET CATEGORIE -->
      <div class="section">
        <div class="section-header">
          <h2>{{ t('setup.budget.title') }}</h2>
        </div>
        <div class="budget-grid">
          <div v-for="cat in expenseCategories" :key="cat.id" class="budget-row">
            <span class="budget-icon">{{ cat.icon }}</span>
            <span class="budget-name">{{ cat.name }}</span>
            <div class="budget-input-wrap">
              <span class="budget-currency">€</span>
              <input class="input input-budget" type="number" min="0"
                v-model="budgetMap[cat.id]"
                @blur="saveBudget(cat.id)"
                placeholder="—" />
            </div>
          </div>
        </div>
      </div>

      <!-- AI -->
      <div class="section">
        <div class="section-header"><h2>{{ t('setup.aiSync.title') }}</h2></div>
        <div class="settings-grid">
          <div class="form-group">
            <label class="label">{{ t('setup.aiSync.providerLabel') }}</label>
            <select class="input" v-model="settings.aiProvider" @change="saveSettings">
              <option value="openai">OpenAI (GPT-4o-mini)</option>
              <option value="anthropic">Anthropic (Claude Haiku)</option>
            </select>
          </div>
        </div>
        <div class="info-box">
          ℹ <span v-html="t('setup.aiSync.infoLine1')"></span>
          {{ t('setup.aiSync.infoLine2') }}
        </div>
      </div>

      <!-- PRIVACY -->
      <div class="section">
        <div class="section-header"><h2>{{ t('setup.privacy.title') }}</h2></div>
        <div class="settings-grid">
          <div class="form-group">
            <label class="label">{{ t('setup.privacy.levelLabel') }}</label>
            <select class="input" v-model="settings.visibilityLevel" @change="saveSettings">
              <option value="segregated">{{ t('setup.privacy.levels.segregated') }}</option>
              <option value="accounts_only">{{ t('setup.privacy.levels.accountsOnly') }}</option>
              <option value="open">{{ t('setup.privacy.levels.open') }}</option>
            </select>
          </div>
        </div>
        <div class="info-box">
          ℹ {{ t('setup.privacy.hint') }}
        </div>
      </div>

      <!-- MANUTENZIONE -->
      <div class="section">
        <div class="section-header"><h2>{{ t('setup.maintenance.title') }}</h2></div>
        <div class="info-box" style="margin-bottom:12px;">
          {{ t('setup.maintenance.hint') }}
        </div>
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
          <button class="btn btn-sm" @click="cleanup" :disabled="cleaning">
            {{ cleaning ? t('setup.maintenance.cleaningInProgress') : ('🧹 ' + t('setup.maintenance.cleanupButton')) }}
          </button>
          <span v-if="cleanResult" class="saved-badge">
            ✓ {{ t('setup.maintenance.result', {
              delPersons: cleanResult.deleted.persons,
              delAccounts: cleanResult.deleted.accounts,
              dbPersons: cleanResult.db.persons,
              dbAccounts: cleanResult.db.accounts,
              dbTransactions: cleanResult.db.transactions,
            }) }}
          </span>
        </div>
      </div>

      <!-- BACKUP -->
      <div class="section">
        <div class="section-header"><h2>{{ t('setup.backup.title') }}</h2></div>
        <div class="info-box" style="margin-bottom:12px;">
          {{ t('setup.backup.hint1') }}
          {{ t('setup.backup.hint2') }}
        </div>
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
          <a class="btn btn-sm" :href="backupExportUrl">⬇ {{ t('setup.backup.exportButton') }}</a>
          <button class="btn btn-sm" @click="triggerBackupFile" :disabled="importingBackup">
            {{ importingBackup ? t('setup.backup.importingInProgress') : ('⬆ ' + t('setup.backup.importButton')) }}
          </button>
          <input ref="backupFileInput" type="file" accept=".xlsx" style="display:none" @change="onBackupFileChange" />
        </div>
        <div v-if="backupResult" class="backup-summary">
          <div v-for="(stats, table) in backupResult" :key="table" class="backup-row">
            <strong>{{ table }}</strong>: {{ t('setup.backup.rowStats', { inserted: stats.inserted, updated: stats.updated }) }}
            <template v-if="stats.skipped">, {{ t('setup.backup.rowSkipped', { skipped: stats.skipped }) }}</template>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../../api.js'

const { t } = useI18n()

const expenseCategories = ref([])
const budgetMap = ref({})
const settings  = ref({ aiProvider: 'openai', visibilityLevel: 'segregated' })
const backendOk = ref(false)
const apiBase   = ref('')
const saved     = ref(false)
const error     = ref('')

function showSaved() {
  error.value = ''
  saved.value = true
  setTimeout(() => { saved.value = false }, 2000)
}
function showError(msg) {
  saved.value = false
  error.value = msg
  setTimeout(() => { error.value = '' }, 4000)
}

async function call(fn) {
  try { return await fn() }
  catch (e) { showError(e?.response?.data?.error || e.message || t('setup.errors.apiError')); return null }
}

// ── Budget ───────────────────────────────────────────
async function saveBudget(catId) {
  const amount = Number(budgetMap.value[catId]) || null
  await call(() => api.put(`api/categories/${catId}`, { budgetMonthly: amount }))
  showSaved()
}

// ── Settings ─────────────────────────────────────────
async function saveSettings() {
  await call(() => api.post('api/setup/complete', {
    aiProvider: settings.value.aiProvider,
    visibilityLevel: settings.value.visibilityLevel,
  }))
  showSaved()
}

// ── Cleanup ───────────────────────────────────────────
const cleaning     = ref(false)
const cleanResult  = ref(null)
async function cleanup() {
  cleaning.value = true
  try {
    const res = await api.post('api/admin/cleanup')
    cleanResult.value = res.data
  } catch (e) { showError(e?.response?.data?.error || e.message) }
  finally { cleaning.value = false }
}

// ── Backup Excel ──────────────────────────────────────
const backupExportUrl = new URL('api/backup/export', document.baseURI).toString()
const backupFileInput = ref(null)
const importingBackup = ref(false)
const backupResult    = ref(null)

function triggerBackupFile() {
  backupFileInput.value?.click()
}

async function onBackupFileChange(e) {
  const file = e.target.files[0]
  if (!file) return
  importingBackup.value = true
  backupResult.value = null
  try {
    const fd = new FormData()
    fd.append('file', file)
    const res = await api.post('api/backup/import', fd)
    backupResult.value = res.data
    showSaved()
  } catch (err) {
    showError(err?.response?.data?.error || err.message || t('setup.errors.backupImportError'))
  } finally {
    importingBackup.value = false
    e.target.value = ''
  }
}

// ── Load ─────────────────────────────────────────────
onMounted(async () => {
  apiBase.value = document.baseURI

  // Test connessione backend
  try {
    await api.get('health')
    backendOk.value = true
  } catch {
    backendOk.value = false
    return
  }

  const cRes = await call(() => api.get('api/categories'))
  const cats = cRes?.data || []
  expenseCategories.value = cats.filter(c => c.type === 'expense')
  expenseCategories.value.forEach(c => { budgetMap.value[c.id] = c.budget_monthly || '' })

  const sRes = await call(() => api.get('api/settings'))
  if (sRes?.data) settings.value = { ...settings.value, ...sRes.data }
})
</script>

<style scoped>
.topbar { background:#fff; border-bottom:1px solid #DDD9D0; padding:0 28px; height:56px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10; }
.topbar-title { font-size:15px; font-weight:600; }
.topbar-actions { display:flex; align-items:center; gap:8px; }
.saved-badge { font-size:12px; color:#2A9D8F; font-weight:500; }
.backup-summary { margin-top:12px; font-size:12.5px; color:#5C5752; display:flex; flex-direction:column; gap:4px; }
.backup-row { text-transform:capitalize; }
.error-badge { font-size:12px; color:#E76F51; font-weight:500; max-width:300px; }

.content { padding:28px; max-width:860px; }

.status-bar { padding:10px 16px; font-size:12px; margin-bottom:24px; display:flex; align-items:center; justify-content:space-between; }
.status-bar.ok   { background:#E6F5F3; color:#2A9D8F; border:1px solid #2A9D8F; }
.status-bar.fail { background:#FCF0EC; color:#E76F51; border:1px solid #E76F51; }
.status-detail { font-family:monospace; font-size:11px; opacity:.7; }

.section { margin-bottom:32px; }
.section-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; padding-bottom:10px; border-bottom:2px solid #1D3557; }
.section-header h2 { font-size:14px; font-weight:600; color:#1D3557; margin:0; }

.input { padding:8px 11px; border:1px solid #DDD9D0; background:#F7F6F2; font-size:13px; font-family:inherit; outline:none; flex:1; min-width:120px; }
.input:focus { border-color:#1D3557; background:#fff; }
.btn { display:inline-flex; align-items:center; padding:7px 14px; font-size:13px; cursor:pointer; border:1px solid #DDD9D0; background:#fff; color:#5C5752; }
.btn-sm { padding:5px 10px; font-size:12px; }

.budget-grid { display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; }
.budget-row { display:flex; align-items:center; gap:8px; padding:8px 12px; background:#fff; border:1px solid #DDD9D0; }
.budget-icon { font-size:16px; flex-shrink:0; }
.budget-name { font-size:12px; flex:1; }
.budget-input-wrap { display:flex; align-items:center; gap:4px; }
.budget-currency { font-size:12px; color:#9A938C; }
.input-budget { width:72px; min-width:0; flex:none; padding:6px 8px; }

.settings-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; max-width:340px; }
.form-group { display:flex; flex-direction:column; gap:6px; }
.label { font-size:12px; font-weight:500; color:#5C5752; }
.info-box { margin-top:16px; padding:12px 16px; background:#EBF0F6; border:1px solid #1D3557; font-size:12px; color:#1D3557; line-height:1.6; }
</style>
