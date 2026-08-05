<template>
  <div>
    <div class="topbar">
      <div>
        <div class="topbar-title">{{ t('dashboard.title') }}</div>
        <div class="topbar-meta">{{ month }}</div>
      </div>
      <div class="topbar-actions">
        <RouterLink to="/transactions" class="btn btn-sm">{{ t('dashboard.actions.addExpense') }}</RouterLink>
        <RouterLink to="/transactions" class="btn btn-primary btn-sm">{{ t('dashboard.actions.import') }}</RouterLink>
      </div>
    </div>

    <div class="content">
      <!-- KPI -->
      <div class="grid-4" v-if="summary">
        <div class="card">
          <div class="card-label">{{ t('dashboard.kpi.monthlyExpenses') }}</div>
          <div class="card-value neg num">{{ fmt(summary.total_expenses) }}</div>
        </div>
        <div class="card">
          <div class="card-label">{{ t('dashboard.kpi.monthlyIncome') }}</div>
          <div class="card-value pos num">{{ fmt(summary.total_income) }}</div>
        </div>
        <div class="card">
          <div class="card-label">{{ t('dashboard.kpi.pendingTransactions') }}</div>
          <div class="card-value num" style="color:var(--amber)">{{ sensors.pending_review ?? '—' }}</div>
          <div class="card-sub" v-if="sensors.pending_review">{{ t('dashboard.kpi.toCategorize') }}</div>
        </div>
        <div class="card">
          <div class="card-label">{{ t('dashboard.kpi.commonAccountsBalance') }}</div>
          <div class="card-value pos num">{{ fmt(sensors.saldo_comuni) }}</div>
        </div>
      </div>

      <!-- Spese personali vs comuni -->
      <div class="card" style="margin-bottom:24px" v-if="destinationBreakdown.length">
        <div class="card-title">{{ t('dashboard.destination.title', { month }) }}</div>
        <div class="dest-bar-track">
          <div v-for="d in destinationBreakdown" :key="d.key" class="dest-bar-seg"
            :style="{ width: d.pct + '%', background: d.color }" :title="`${d.label}: ${fmt(d.total)}`"></div>
        </div>
        <div class="dest-legend">
          <div v-for="d in destinationBreakdown" :key="d.key" class="dest-legend-item">
            <span class="dest-dot" :style="{ background: d.color }"></span>
            <span class="dest-label">{{ d.label }}</span>
            <span class="num dest-value">{{ fmt(d.total) }}</span>
          </div>
        </div>
      </div>

      <!-- Andamento spese -->
      <div class="card" style="margin-bottom:24px">
        <div class="card-title">{{ t('dashboard.trend.title') }}</div>
        <TrendChart :rows="trend" />
      </div>

      <!-- Budget per categoria -->
      <div class="grid-2-1" v-if="summary">
        <div class="card">
          <div class="card-title">{{ t('dashboard.budget.titleWithMonth', { month }) }}</div>
          <div v-if="summary.byCategory?.length">
            <div v-for="cat in summary.byCategory" :key="cat.id" class="cat-bar">
              <div class="cat-bar-header">
                <span>{{ cat.icon }} {{ cat.name }}</span>
                <span class="num" :class="cat.budget_monthly && cat.spent > cat.budget_monthly ? 'text-coral' : ''">
                  {{ fmt(cat.spent) }}{{ cat.budget_monthly ? ' / ' + fmt(cat.budget_monthly) : '' }}
                </span>
              </div>
              <div class="bar-track" v-if="cat.budget_monthly">
                <div class="bar-fill"
                  :style="{ width: Math.min(100, (cat.spent/cat.budget_monthly)*100) + '%', background: cat.spent > cat.budget_monthly ? 'var(--coral)' : 'var(--navy)' }">
                </div>
              </div>
              <div class="cat-bar-header" v-if="cat.budget_annual" style="margin-top:4px">
                <span class="cat-bar-sub">{{ t('dashboard.budget.annual') }}</span>
                <span class="num cat-bar-sub" :class="cat.spent_year > cat.budget_annual ? 'text-coral' : ''">
                  {{ fmt(cat.spent_year) }} / {{ fmt(cat.budget_annual) }}
                </span>
              </div>
              <div class="bar-track" v-if="cat.budget_annual">
                <div class="bar-fill"
                  :style="{ width: Math.min(100, (cat.spent_year/cat.budget_annual)*100) + '%', background: cat.spent_year > cat.budget_annual ? 'var(--coral)' : 'var(--amber)' }">
                </div>
              </div>
            </div>
          </div>
          <div v-else class="empty">{{ t('dashboard.budget.noTransactions') }}</div>
        </div>

        <div class="card">
          <div class="card-title">{{ t('dashboard.sensors.title') }}</div>
          <div class="sensor-row"><span>{{ t('dashboard.sensors.budgetOkMonth') }}</span><span :class="sensors.budget_ok ? 'ok' : 'warn'">{{ sensors.budget_ok ? '✓' : '✗' }}</span></div>
          <div class="sensor-row"><span>{{ t('dashboard.sensors.budgetOkYear') }}</span><span :class="sensors.budget_ok_annual ? 'ok' : 'warn'">{{ sensors.budget_ok_annual ? '✓' : '✗' }}</span></div>
          <div class="sensor-row"><span>{{ t('dashboard.sensors.expensesToday') }}</span><span class="num">{{ fmt(sensors.spese_oggi) }}</span></div>
          <div class="sensor-row"><span>{{ t('dashboard.sensors.expensesYear') }}</span><span class="num">{{ fmt(sensors.spese_anno) }}</span></div>
          <div v-if="sensors.over_budget?.length" class="over-budget-list">
            <div class="card-label" style="margin-top:12px">{{ t('dashboard.sensors.monthlyOverBudget') }}</div>
            <div v-for="name in sensors.over_budget" :key="name" class="over-budget-item">⚠ {{ name }}</div>
          </div>
          <div v-if="sensors.over_budget_annual?.length" class="over-budget-list">
            <div class="card-label" style="margin-top:12px">{{ t('dashboard.sensors.annualOverBudget') }}</div>
            <div v-for="name in sensors.over_budget_annual" :key="name" class="over-budget-item">⚠ {{ name }}</div>
          </div>
        </div>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="empty">{{ t('dashboard.loading') }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api as axios } from '../api.js'
import TrendChart from '../components/TrendChart.vue'

const { t } = useI18n()
const month = new Date().toLocaleDateString('it-IT', { month: 'long', year: 'numeric' })
const monthKey = new Date().toISOString().slice(0, 7)
const summary = ref(null)
const sensors = ref({})
const trend = ref([])
const loading = ref(true)

function fmt(v) {
  if (v == null) return '—'
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v)
}

// Spese del mese per destinazione (byDestination gia' rispetta la
// visibilita' dell'utente collegato: 'personal' qui e' gia' solo la sua
// quota, non quella di tutta la famiglia - vedi access.transaction_visibility).
const destinationBreakdown = computed(() => {
  const rows = summary.value?.byDestination || []
  const totals = { family: 0, personal: 0, split: 0 }
  for (const r of rows) {
    if (r.destination in totals) totals[r.destination] += r.total
  }
  const grandTotal = totals.family + totals.personal + totals.split
  if (!grandTotal) return []
  const defs = [
    { key: 'family',   label: t('dashboard.destination.family'),   color: '#1D3557' },
    { key: 'personal', label: t('dashboard.destination.personal'), color: '#E8A020' },
    { key: 'split',    label: t('dashboard.destination.split'),    color: '#2A9D8F' },
  ]
  return defs
    .map(d => ({ ...d, total: totals[d.key], pct: (totals[d.key] / grandTotal) * 100 }))
    .filter(d => d.total > 0)
})

onMounted(async () => {
  try {
    const [s, h, tr] = await Promise.all([
      axios.get(`api/reports/summary?month=${monthKey}`),
      axios.get('api/ha/sensors'),
      axios.get('api/reports/trend?months=6'),
    ])
    summary.value = s.data
    sensors.value = h.data
    trend.value = Array.isArray(tr.data) ? tr.data : []
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.topbar { background:#fff; border-bottom:1px solid #DDD9D0; padding:0 28px; height:56px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10; }
.topbar-title { font-size:15px; font-weight:600; }
.topbar-meta { font-size:12px; color:#9A938C; }
.topbar-actions { display:flex; gap:8px; }
.content { padding:28px; }
.grid-4 { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:24px; }
.grid-2-1 { display:grid; grid-template-columns:2fr 1fr; gap:16px; }
.card { background:#fff; border:1px solid #DDD9D0; padding:20px; }
.card-label { font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:#9A938C; margin-bottom:6px; }
.card-title { font-size:13px; font-weight:600; margin-bottom:16px; }
.card-value { font-size:26px; font-weight:300; letter-spacing:-.02em; }
.card-sub { font-size:12px; color:#9A938C; margin-top:4px; }
.card-value.pos { color:#2A9D8F; }
.card-value.neg { color:#E76F51; }
.cat-bar { margin-bottom:14px; }
.cat-bar-header { display:flex; justify-content:space-between; font-size:12px; margin-bottom:5px; }
.cat-bar-sub { font-size:10px; color:#9A938C; }
.bar-track { height:6px; background:#F0EEE9; }
.bar-fill { height:100%; transition:width .4s; }
.text-coral { color:#E76F51; }
.empty { text-align:center; padding:40px; color:#9A938C; font-size:13px; }
.btn { display:inline-flex; align-items:center; gap:6px; padding:7px 14px; font-size:13px; font-weight:500; cursor:pointer; border:1px solid #DDD9D0; background:#fff; color:#5C5752; text-decoration:none; }
.btn-primary { background:#1D3557; color:#fff; border-color:#1D3557; }
.btn-sm { padding:5px 10px; font-size:12px; }
.sensor-row { display:flex; justify-content:space-between; font-size:12px; padding:6px 0; border-bottom:1px solid #F0EEE9; }
.ok { color:#2A9D8F; font-weight:600; }
.warn { color:#E76F51; font-weight:600; }
.over-budget-item { font-size:12px; color:#E8A020; padding:3px 0; }
.dest-bar-track { height:10px; background:#F0EEE9; display:flex; overflow:hidden; margin-bottom:14px; }
.dest-bar-seg { height:100%; }
.dest-legend { display:flex; flex-wrap:wrap; gap:20px; }
.dest-legend-item { display:flex; align-items:center; gap:7px; font-size:12.5px; }
.dest-dot { width:9px; height:9px; border-radius:50%; flex-shrink:0; }
.dest-label { color:#5C5752; }
.dest-value { font-weight:600; }
</style>
