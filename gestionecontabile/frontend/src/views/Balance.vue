<template>
  <div>
    <div class="topbar">
      <div class="topbar-title">{{ t('balance.title') }}</div>
      <div class="topbar-actions">
        <select class="input-sel" v-model="period" @change="load">
          <option value="month">{{ t('balance.period.month') }}</option>
          <option value="all">{{ t('balance.period.all') }}</option>
        </select>
        <input v-if="period==='month'" class="input-sel" type="month" v-model="month" @change="load" />
      </div>
    </div>

    <div class="content">
      <div v-if="loading" class="empty">{{ t('balance.loading') }}</div>
      <div v-else-if="error" class="empty err">{{ error }}</div>
      <div v-else-if="!data.persons?.length" class="empty">
        {{ t('balance.empty.text', { paidBy: t('balance.note.paidBy') }) }}
      </div>

      <template v-else>

        <!-- Riepilogo chi deve cosa -->
        <div v-if="data.debt" class="debt-banner">
          <div class="debt-icon">⚖️</div>
          <div>
            <strong>{{ data.debt.debtor }}</strong> {{ t('balance.debt.owes') }}
            <strong class="debt-amount">{{ fmt(data.debt.amount) }}</strong>
            {{ t('balance.debt.to') }} <strong>{{ data.debt.creditor }}</strong>
          </div>
        </div>
        <div v-else class="debt-banner balanced">
          <div class="debt-icon">✓</div>
          <div>{{ t('balance.debt.balanced') }}</div>
        </div>

        <!-- Card per persona -->
        <div class="person-cards">
          <div v-for="p in data.persons" :key="p.id" class="person-card">
            <div class="card-header" :style="{ borderTopColor: p.color || '#1D3557' }">
              <div class="person-avatar" :style="{ background: p.color || '#1D3557' }">
                {{ initials(p.name) }}
              </div>
              <div class="person-name">{{ p.name }}</div>
              <div class="person-net" :class="p.net >= 0 ? 'pos' : 'neg'">
                {{ p.net >= 0 ? '+' : '' }}{{ fmt(p.net) }}
              </div>
            </div>

            <div class="card-body">
              <div class="row-stat contributed">
                <span class="stat-label">↑ {{ t('balance.stats.contributed') }}</span>
                <span class="stat-value pos">+{{ fmt(p.contributed) }}</span>
              </div>
              <div class="row-stat">
                <span class="stat-label">↓ {{ t('balance.stats.familySpent') }}</span>
                <span class="stat-value neg">−{{ fmt(p.familySpent) }}</span>
              </div>
              <div class="row-stat">
                <span class="stat-label">↓ {{ t('balance.stats.personalSpent') }}</span>
                <span class="stat-value neg">−{{ fmt(p.personalSpent) }}</span>
              </div>
              <div class="row-total">
                <span class="stat-label">{{ t('balance.stats.netBalance') }}</span>
                <span class="stat-value" :class="p.net >= 0 ? 'pos' : 'neg'">
                  {{ p.net >= 0 ? '+' : '' }}{{ fmt(p.net) }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Nota metodologica -->
        <div class="note">
          <strong>{{ t('balance.note.title') }}</strong>
          {{ t('balance.note.body') }}
          {{ t('balance.note.footerBefore') }} <em>{{ t('balance.note.paidBy') }}</em> {{ t('balance.note.footerAfter') }}
        </div>

      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'

const { t } = useI18n()

const loading = ref(true)
const error   = ref('')
const data    = ref({})
const period  = ref('month')
const month   = ref(new Date().toISOString().slice(0, 7))

const fmt = v => new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v)
const initials = name => (name || '').split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ period: period.value })
    if (period.value === 'month') params.set('month', month.value)
    const res = await api.get(`api/reports/balance?${params}`)
    data.value = res.data
  } catch (e) {
    error.value = e?.response?.data?.error || e.message || t('balance.errors.loadFailed')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.topbar { background:#fff; border-bottom:1px solid #DDD9D0; padding:0 28px; height:56px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10; }
.topbar-title { font-size:15px; font-weight:600; }
.topbar-actions { display:flex; gap:8px; align-items:center; }
.input-sel { padding:6px 10px; border:1px solid #DDD9D0; background:#F7F6F2; font-size:13px; font-family:inherit; outline:none; }

.content { padding:28px; max-width:860px; }
.empty { text-align:center; padding:60px; color:#9A938C; font-size:13px; }
.err   { color:#E76F51; }

.debt-banner { display:flex; align-items:center; gap:16px; padding:18px 24px; border:1px solid #E76F51; background:#FCF0EC; color:#E76F51; font-size:14px; margin-bottom:24px; }
.debt-banner.balanced { border-color:#2A9D8F; background:#E6F5F3; color:#2A9D8F; }
.debt-icon   { font-size:22px; }
.debt-amount { font-size:16px; }

.person-cards { display:grid; grid-template-columns:repeat(auto-fit, minmax(300px,1fr)); gap:16px; margin-bottom:24px; }
.person-card  { background:#fff; border:1px solid #DDD9D0; border-top:3px solid #1D3557; }
.card-header  { display:flex; align-items:center; gap:12px; padding:16px 20px; border-bottom:1px solid #DDD9D0; }
.person-avatar { width:36px; height:36px; display:grid; place-items:center; font-size:13px; font-weight:700; color:#fff; flex-shrink:0; }
.person-name   { flex:1; font-size:14px; font-weight:600; }
.person-net    { font-size:18px; font-weight:700; font-variant-numeric:tabular-nums; }

.card-body  { padding:16px 20px; display:flex; flex-direction:column; gap:10px; }
.row-stat   { display:flex; justify-content:space-between; align-items:center; font-size:13px; }
.row-total  { display:flex; justify-content:space-between; align-items:center; font-size:13px; font-weight:600; padding-top:10px; border-top:1px solid #DDD9D0; }
.stat-label { color:#5C5752; }
.stat-value { font-variant-numeric:tabular-nums; font-weight:500; }
.pos { color:#2A9D8F; }
.neg { color:#E76F51; }

.note { font-size:12px; color:#9A938C; line-height:1.7; padding:14px 18px; background:#F7F6F2; border:1px solid #DDD9D0; }
</style>
