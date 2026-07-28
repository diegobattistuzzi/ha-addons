<template>
  <div>
    <div class="topbar">
      <div class="topbar-title">{{ t('reports.title') }}</div>
      <div class="topbar-actions">
        <button class="btn btn-sm">↓ {{ t('reports.exportPdf') }}</button>
      </div>
    </div>
    <div class="content">
      <div class="tab-row">
        <button class="tab-btn" :class="{ active: mode === 'andamento' }" @click="mode = 'andamento'">{{ t('reports.tabs.trend') }}</button>
        <button class="tab-btn" :class="{ active: mode === 'custom' }" @click="mode = 'custom'">{{ t('reports.tabs.custom') }}</button>
      </div>

      <ReportBuilder v-if="mode === 'custom'" />

      <template v-else>
      <div class="period-row">
        <button v-for="p in periods" :key="p.value" class="period-btn" :class="{ active: period === p.value }" @click="period = p.value">{{ p.label }}</button>
        <input class="input period-picker" type="month" v-model="period" />
        <select class="input period-picker" v-model="accountId">
          <option value="">{{ t('reports.allAccounts') }}</option>
          <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
        </select>
      </div>

      <div class="card" style="margin-bottom:16px">
        <div class="card-title">{{ t('reports.monthlyTrend') }}</div>
        <TrendChart :rows="trend" />
      </div>

      <div class="grid-2">
        <div class="card">
          <div class="card-title">{{ t('reports.expensesByCategory') }}</div>
          <div v-if="summary?.byCategory?.length">
            <div v-for="cat in summary.byCategory" :key="cat.id" class="cat-bar">
              <div class="cat-bar-header">
                <span>{{ cat.icon }} {{ cat.name }}</span>
                <span class="num" :class="cat.budget_monthly && cat.spent > cat.budget_monthly ? 'over' : ''">{{ fmt(cat.spent) }}</span>
              </div>
              <div class="bar-track">
                <div class="bar-fill" :style="{ width: cat.budget_monthly ? Math.min(100,(cat.spent/cat.budget_monthly)*100)+'%' : '100%', background: cat.spent > (cat.budget_monthly||Infinity) ? '#E76F51' : '#1D3557' }"></div>
              </div>
              <div class="cat-bar-header" v-if="cat.budget_annual" style="margin-top:4px">
                <span class="cat-bar-sub">{{ t('reports.annual') }}</span>
                <span class="num cat-bar-sub" :class="cat.spent_year > cat.budget_annual ? 'over' : ''">{{ fmt(cat.spent_year) }} / {{ fmt(cat.budget_annual) }}</span>
              </div>
              <div class="bar-track" v-if="cat.budget_annual">
                <div class="bar-fill" :style="{ width: Math.min(100,(cat.spent_year/cat.budget_annual)*100)+'%', background: cat.spent_year > cat.budget_annual ? '#E76F51' : '#E8A020' }"></div>
              </div>
            </div>
          </div>
          <div v-else class="empty">{{ t('reports.noDataPeriod') }}</div>
        </div>

        <div style="display:flex;flex-direction:column;gap:16px">
          <div class="card" v-if="summary?.byDestination?.length">
            <div class="card-title">{{ t('reports.personalVsFamily') }}</div>
            <div v-for="d in summary.byDestination" :key="d.destination" class="summary-row">
              <span>{{ destinationLabel(d.destination) }}</span>
              <span class="num neg">{{ fmt(d.total) }}</span>
            </div>
          </div>

          <div class="card">
            <div class="card-title">{{ t('reports.summary') }}</div>
            <div class="summary-row"><span>{{ t('reports.totalExpensesMonth') }}</span><span class="num neg">{{ fmt(summary?.total_expenses) }}</span></div>
            <div class="summary-row"><span>{{ t('reports.totalIncomeMonth') }}</span><span class="num pos">{{ fmt(summary?.total_income) }}</span></div>
            <div class="summary-row" style="border-top:2px solid #DDD9D0;margin-top:8px;padding-top:8px;font-weight:600">
              <span>{{ t('reports.balanceMonth') }}</span>
              <span class="num" :class="(summary?.total_income - summary?.total_expenses) >= 0 ? 'pos' : 'neg'">
                {{ fmt((summary?.total_income || 0) - (summary?.total_expenses || 0)) }}
              </span>
            </div>
            <div class="summary-row" style="margin-top:8px"><span>{{ t('reports.totalExpensesYear') }}</span><span class="num neg">{{ fmt(summary?.total_expenses_year) }}</span></div>
            <div class="summary-row"><span>{{ t('reports.totalIncomeYear') }}</span><span class="num pos">{{ fmt(summary?.total_income_year) }}</span></div>
          </div>

          <div class="card">
            <div class="card-title">{{ t('reports.expenseComparison') }}</div>
            <div class="compare-row">
              <span>{{ t('reports.vsLastMonth') }}</span>
              <span class="delta" :class="deltaClass(expenseDeltaMonth)">{{ deltaLabel(expenseDeltaMonth) }}</span>
            </div>
            <div class="compare-row">
              <span>{{ t('reports.vsSameMonthLastYear', { month: sameMonthLastYearLabel }) }}</span>
              <span class="delta" :class="deltaClass(expenseDeltaYear)">{{ deltaLabel(expenseDeltaYear) }}</span>
            </div>
          </div>

          <div class="card">
            <div class="card-title">{{ t('reports.topMerchantsMonth') }}</div>
            <div v-if="topMerchants.length">
              <div v-for="(m, i) in topMerchants" :key="m.merchant_name" class="summary-row">
                <span>{{ i + 1 }}. {{ m.merchant_name }} <span class="cat-bar-sub">{{ t('reports.occurrences', { count: m.occurrences }) }}</span></span>
                <span class="num neg">{{ fmt(m.total) }}</span>
              </div>
            </div>
            <div v-else class="empty" style="padding:20px">{{ t('reports.noExpensesPeriod') }}</div>
          </div>

          <div class="card">
            <div class="card-title">{{ t('reports.activeSubscriptions') }}</div>
            <div v-if="subscriptions.length">
              <div v-for="s in subscriptions.slice(0,5)" :key="s.merchant_name" class="summary-row">
                <span>{{ s.merchant_name }}</span>
                <span class="num">{{ t('reports.perMonthAmount', { amount: fmt(s.amount) }) }}</span>
              </div>
              <div class="summary-row" style="font-weight:600;border-top:1px solid #DDD9D0;margin-top:8px;padding-top:8px">
                <span>{{ t('common.total') }}</span>
                <span class="num">{{ t('reports.perMonthAmount', { amount: fmt(subTotal) }) }}</span>
              </div>
            </div>
            <div v-else class="empty" style="padding:20px">{{ t('reports.noSubscriptions') }}</div>
          </div>
        </div>
      </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api as axios } from '../api.js'
import TrendChart from '../components/TrendChart.vue'
import ReportBuilder from '../components/ReportBuilder.vue'

const { t } = useI18n()

const mode = ref('andamento')
const period = ref(new Date().toISOString().slice(0,7))
const accountId = ref('')
const accounts = ref([])

function destinationLabel(d) {
  const labels = { family: t('reports.destinations.family'), personal: t('reports.destinations.personal'), split: t('reports.destinations.split') }
  return labels[d] || d || '—'
}

// Scorciatoie per gli ultimi mesi: qualunque altro mese si sceglie col
// selettore libero qui sotto, il backend accetta gia' qualsiasi 'YYYY-MM'.
const periods = (() => {
  const arr = []
  const d = new Date()
  d.setDate(1)
  for (let i = 0; i < 6; i++) {
    arr.push({
      value: d.toISOString().slice(0,7),
      label: d.toLocaleDateString('it-IT', { month: 'short', year: 'numeric' }),
    })
    d.setMonth(d.getMonth() - 1)
  }
  return arr
})()
const summary = ref(null)
const subscriptions = ref([])
const trend = ref([])
const topMerchants = ref([])
const subTotal = computed(() => subscriptions.value.reduce((s,r) => s + r.amount, 0))

// Variazione percentuale delle spese vs un periodo di confronto: null quando il
// periodo di confronto non ha spese (divisione per zero non significativa, es.
// conto aperto da poco) - in quel caso non mostriamo una percentuale.
function pctDelta(current, previous) {
  if (!previous) return null
  return ((current - previous) / previous) * 100
}
const expenseDeltaMonth = computed(() => pctDelta(summary.value?.total_expenses, summary.value?.previousMonth?.total_expenses))
const expenseDeltaYear = computed(() => pctDelta(summary.value?.total_expenses, summary.value?.previousYearSameMonth?.total_expenses))

const sameMonthLastYearLabel = computed(() => {
  const [y, mo] = period.value.split('-')
  const d = new Date(Number(y) - 1, Number(mo) - 1, 1)
  return d.toLocaleDateString('it-IT', { month: 'long', year: 'numeric' })
})

function deltaLabel(pct) {
  if (pct == null) return t('reports.notAvailable')
  const sign = pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(0)}%`
}
// Per le SPESE, un aumento e' "peggio" (rosso) e una diminuzione e' "meglio"
// (verde) - il contrario della convenzione .pos/.neg usata per gli importi.
function deltaClass(pct) {
  if (pct == null) return ''
  return pct > 0 ? 'neg' : 'pos'
}

function fmt(v) {
  if (v == null) return '—'
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v)
}

async function load() {
  const acc = accountId.value ? `&accountId=${accountId.value}` : ''
  const [s, sub, tr, top] = await Promise.all([
    axios.get(`api/reports/summary?month=${period.value}${acc}`),
    axios.get('api/reports/subscriptions'),
    axios.get(`api/reports/trend?months=6${acc}`),
    axios.get(`api/reports/top-merchants?month=${period.value}&limit=5${acc}`),
  ])
  summary.value = s.data
  subscriptions.value = sub.data.subscriptions || []
  trend.value = Array.isArray(tr.data) ? tr.data : []
  topMerchants.value = Array.isArray(top.data) ? top.data : []
}

async function loadAccounts() {
  const res = await axios.get('api/accounts')
  accounts.value = Array.isArray(res.data) ? res.data : []
}

watch([period, accountId], load)
onMounted(() => { loadAccounts(); load() })
</script>

<style scoped>
.topbar { background:#fff; border-bottom:1px solid #DDD9D0; padding:0 28px; height:56px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10; }
.topbar-title { font-size:15px; font-weight:600; }
.topbar-actions { display:flex; gap:8px; }
.content { padding:28px; }
.tab-row { display:flex; gap:8px; margin-bottom:20px; }
.tab-btn { padding:8px 18px; border:1px solid #DDD9D0; font-size:12.5px; cursor:pointer; background:#fff; color:#5C5752; }
.tab-btn.active { background:#1D3557; color:#fff; border-color:#1D3557; }
.period-row { display:flex; align-items:center; gap:8px; margin-bottom:24px; flex-wrap:wrap; }
.period-btn { padding:7px 16px; border:1px solid #DDD9D0; font-size:12px; cursor:pointer; background:#fff; color:#5C5752; margin-right:-1px; text-transform:capitalize; }
.period-btn.active { background:#1D3557; color:#fff; border-color:#1D3557; z-index:1; position:relative; }
.input { padding:8px 11px; border:1px solid #DDD9D0; background:#F7F6F2; font-size:13px; font-family:inherit; outline:none; }
.input:focus { border-color:#1D3557; background:#fff; }
.period-picker { margin-left:8px; }
.btn { display:inline-flex; align-items:center; padding:7px 14px; font-size:13px; cursor:pointer; border:1px solid #DDD9D0; background:#fff; color:#5C5752; }
.btn-sm { padding:5px 10px; font-size:12px; }
.grid-2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
.card { background:#fff; border:1px solid #DDD9D0; padding:20px; }
.card-title { font-size:13px; font-weight:600; margin-bottom:16px; }
.cat-bar { margin-bottom:14px; }
.cat-bar-header { display:flex; justify-content:space-between; font-size:12px; margin-bottom:5px; }
.cat-bar-sub { font-size:10px; color:#9A938C; }
.bar-track { height:6px; background:#F0EEE9; }
.bar-fill { height:100%; transition:width .4s; }
.summary-row { display:flex; justify-content:space-between; font-size:12px; padding:6px 0; border-bottom:1px solid #F0EEE9; }
.summary-row:last-child { border-bottom:none; }
.neg { color:#E76F51; }
.pos { color:#2A9D8F; }
.over { color:#E76F51; }
.empty { text-align:center; padding:40px; color:#9A938C; font-size:13px; }
.compare-row { display:flex; justify-content:space-between; align-items:center; font-size:12px; padding:7px 0; border-bottom:1px solid #F0EEE9; }
.compare-row:last-child { border-bottom:none; }
.delta { font-weight:600; font-variant-numeric:tabular-nums; }
</style>
