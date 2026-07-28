<template>
  <div>
    <div class="topbar">
      <div>
        <div class="topbar-title">{{ t('bankSync.title') }}</div>
        <div class="topbar-meta">{{ t('bankSync.subtitle') }}</div>
      </div>
      <div class="topbar-actions">
        <button class="btn btn-primary btn-sm" @click="syncNow" :disabled="syncing">
          {{ syncing ? t('bankSync.syncingButton') : t('bankSync.syncNowButton') }}
        </button>
      </div>
    </div>

    <div class="content">
      <div v-if="!status.hasCredentials" class="info-banner">
        {{ t('bankSync.notConfigured') }}
        <RouterLink to="/setup" class="link">{{ t('bankSync.addCredentialsLink') }}</RouterLink>
      </div>

      <div class="section-title">{{ t('bankSync.statusSectionTitle') }}</div>
      <div class="grid-3" style="margin-bottom:24px">
        <div class="card"><div class="card-label">{{ t('bankSync.connectedAccounts') }}</div><div class="card-value">{{ status.connected ?? '—' }}</div></div>
        <div class="card"><div class="card-label">{{ t('bankSync.lastSync') }}</div><div class="card-value-sm">{{ status.lastSync ? new Date(status.lastSync).toLocaleString('it-IT') : t('bankSync.never') }}</div></div>
        <div class="card"><div class="card-label">{{ t('bankSync.status') }}</div><div :class="status.lastError ? 'error' : 'ok-text'">{{ status.lastError || t('bankSync.ok') }}</div></div>
      </div>

      <div class="section-title">{{ t('bankSync.logSectionTitle') }}</div>
      <div class="log-box">
        <div v-if="!log.length" style="color:#4A5568">{{ t('bankSync.noSyncYet') }}</div>
        <div v-for="entry in log" :key="entry.id">
          <span class="log-time">{{ entry.synced_at }}</span>
          <span :class="entry.error ? 'log-warn' : 'log-ok'">
            [{{ entry.error ? t('bankSync.logErr') : t('bankSync.logOk') }}]
          </span>
          {{ t('bankSync.logEntry', { accountId: entry.account_id, txNew: entry.tx_new, txDuplicate: entry.tx_duplicate }) }}
          <span v-if="entry.error" style="color:#FC8181"> {{ entry.error }}</span>
        </div>
      </div>

      <div class="section-title" style="margin-top:24px">{{ t('bankSync.haSectionTitle') }}</div>
      <div class="code-block">
        <pre>{{ haYaml }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api as axios } from '../api.js'

const { t } = useI18n()

const status = ref({})
const log = ref([])
const syncing = ref(false)

const haYaml = `# configuration.yaml
rest:
  - scan_interval: 300
    resource: http://localhost:8099/api/ha/sensors
    sensor:
      - name: "CasaSpese Spese Mese"
        value_template: "{{ value_json.spese_mese }}"
        unit_of_measurement: "EUR"
      - name: "CasaSpese Budget OK"
        value_template: "{{ value_json.budget_ok }}"
      - name: "CasaSpese Pending Review"
        value_template: "{{ value_json.pending_review }}"`

async function syncNow() {
  syncing.value = true
  try {
    await axios.post('api/banksync/sync')
    await loadData()
  } catch {}
  syncing.value = false
}

async function loadData() {
  const [s, l] = await Promise.all([
    axios.get('api/banksync/status'),
    axios.get('api/banksync/log?limit=20'),
  ])
  status.value = s.data
  log.value = l.data
}

onMounted(loadData)
</script>

<style scoped>
.topbar { background:#fff; border-bottom:1px solid #DDD9D0; padding:0 28px; height:56px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10; }
.topbar-title { font-size:15px; font-weight:600; }
.topbar-meta { font-size:12px; color:#9A938C; }
.topbar-actions { display:flex; gap:8px; }
.content { padding:28px; }
.btn { display:inline-flex; align-items:center; padding:7px 14px; font-size:13px; cursor:pointer; border:1px solid #DDD9D0; background:#fff; color:#5C5752; }
.btn-primary { background:#1D3557; color:#fff; border-color:#1D3557; }
.btn-sm { padding:5px 10px; font-size:12px; }
.btn:disabled { opacity:.5; cursor:not-allowed; }
.info-banner { background:#FEF5E7; border:1px solid #E8A020; padding:12px 16px; font-size:13px; color:#7a4f00; margin-bottom:20px; }
.link { color:#1D3557; text-decoration:underline; }
.section-title { font-size:13px; font-weight:600; margin-bottom:12px; }
.grid-3 { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }
.card { background:#fff; border:1px solid #DDD9D0; padding:20px; }
.card-label { font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:#9A938C; margin-bottom:6px; }
.card-value { font-size:26px; font-weight:300; }
.card-value-sm { font-size:13px; font-weight:500; margin-top:4px; }
.ok-text { color:#2A9D8F; font-weight:600; margin-top:4px; }
.error { color:#E76F51; font-weight:600; margin-top:4px; }
.log-box { background:#0A0E1A; color:#7ee8a2; font-family:monospace; font-size:12px; padding:16px; line-height:1.8; overflow-x:auto; }
.log-time { color:#4A5568; margin-right:8px; }
.log-ok { color:#68D391; }
.log-warn { color:#F6AD55; }
.code-block { background:#1A1917; color:#E6EDF3; font-family:monospace; font-size:12px; padding:16px; overflow-x:auto; }
.code-block pre { margin:0; white-space:pre; }
</style>
