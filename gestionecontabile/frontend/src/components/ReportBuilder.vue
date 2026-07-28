<template>
  <div>
    <div class="card" style="margin-bottom:16px">
      <div class="card-title">{{ t('reportBuilder.savedReports.title') }}</div>
      <div class="saved-row">
        <select class="input" v-model="selectedReportId" @change="onSelectSaved">
          <option value="">{{ t('reportBuilder.savedReports.newReportOption') }}</option>
          <option v-for="r in savedReports" :key="r.id" :value="r.id">{{ r.name }}</option>
        </select>
        <button class="btn btn-sm" @click="saveAsNew">💾 {{ t('reportBuilder.savedReports.saveAsNew') }}</button>
        <button v-if="selectedReportId" class="btn btn-sm" @click="updateCurrent">{{ t('reportBuilder.savedReports.updateReport', { name: currentName }) }}</button>
        <button v-if="selectedReportId" class="btn-icon danger" @click="deleteCurrent" :title="t('reportBuilder.savedReports.deleteReportTitle')">✕</button>
      </div>
    </div>

    <div class="card" style="margin-bottom:16px">
      <div class="card-title">{{ t('reportBuilder.builder.title') }}</div>
      <div class="builder-grid">
        <div class="form-group">
          <label class="label">{{ t('reportBuilder.builder.groupBy') }}</label>
          <select class="input" v-model="config.dimensions[0]">
            <option v-for="d in dimensionOptions" :key="d.value" :value="d.value">{{ d.label }}</option>
          </select>
        </div>
        <div class="form-group">
          <label class="label">{{ t('reportBuilder.builder.splitBy') }}</label>
          <select class="input" v-model="secondDimension">
            <option value="">{{ t('reportBuilder.builder.noneOption') }}</option>
            <option v-for="d in dimensionOptions" :key="d.value" :value="d.value" :disabled="d.value === config.dimensions[0]">{{ d.label }}</option>
          </select>
        </div>
        <div class="form-group">
          <label class="label">{{ t('reportBuilder.builder.metric') }}</label>
          <select class="input" v-model="config.metric">
            <option value="sum">{{ t('reportBuilder.metrics.sum') }}</option>
            <option value="count">{{ t('reportBuilder.metrics.count') }}</option>
            <option value="avg">{{ t('reportBuilder.metrics.avg') }}</option>
          </select>
        </div>
        <div class="form-group">
          <label class="label">{{ t('reportBuilder.builder.visualization') }}</label>
          <select class="input" v-model="config.chartType">
            <option value="table">{{ t('reportBuilder.chartTypes.table') }}</option>
            <option value="bar">{{ t('reportBuilder.chartTypes.bar') }}</option>
            <option value="pie">{{ t('reportBuilder.chartTypes.pie') }}</option>
          </select>
        </div>
      </div>

      <div class="builder-grid" style="margin-top:12px">
        <div class="form-group">
          <label class="label">{{ t('reportBuilder.builder.dateFrom') }}</label>
          <input class="input" type="date" v-model="config.filters.dateFrom" />
        </div>
        <div class="form-group">
          <label class="label">{{ t('reportBuilder.builder.dateTo') }}</label>
          <input class="input" type="date" v-model="config.filters.dateTo" />
        </div>
        <div class="form-group">
          <label class="label">{{ t('reportBuilder.builder.type') }}</label>
          <select class="input" v-model="config.filters.type">
            <option value="">{{ t('reportBuilder.builder.allTypes') }}</option>
            <option value="expense">{{ t('reportBuilder.builder.expenseOnly') }}</option>
            <option value="income">{{ t('reportBuilder.builder.incomeOnly') }}</option>
          </select>
        </div>
        <div class="form-group">
          <label class="check" style="padding-top:24px">
            <input type="checkbox" v-model="config.filters.confirmedOnly" /> {{ t('reportBuilder.builder.confirmedOnly') }}
          </label>
        </div>
      </div>

      <div class="builder-grid" style="margin-top:12px">
        <div class="form-group">
          <label class="label">{{ t('reportBuilder.builder.account') }}</label>
          <select class="input" v-model="config.filters.accountId">
            <option value="">{{ t('reportBuilder.builder.allAccounts') }}</option>
            <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select>
        </div>
        <div class="form-group">
          <label class="label">{{ t('reportBuilder.builder.category') }}</label>
          <select class="input" v-model="config.filters.categoryId">
            <option value="">{{ t('reportBuilder.builder.allCategories') }}</option>
            <option v-for="c in categoriesTree" :key="c.id" :value="c.id">{{ c.depth ? '↳ ' : '' }}{{ c.name }}</option>
          </select>
        </div>
        <div class="form-group">
          <label class="label">{{ t('reportBuilder.builder.person') }}</label>
          <select class="input" v-model="config.filters.personId">
            <option value="">{{ t('reportBuilder.builder.allPersons') }}</option>
            <option v-for="p in persons" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
        <div class="form-group">
          <label class="label">{{ t('reportBuilder.builder.destination') }}</label>
          <select class="input" v-model="config.filters.destination">
            <option value="">{{ t('reportBuilder.builder.allDestinations') }}</option>
            <option value="family">{{ t('reportBuilder.builder.familyOnly') }}</option>
            <option value="personal">{{ t('reportBuilder.builder.personalOnly') }}</option>
            <option value="split">{{ t('reportBuilder.builder.splitOnly') }}</option>
          </select>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">{{ t('reportBuilder.result.title') }}</div>
      <div v-if="loading" class="empty">{{ t('reportBuilder.result.loading') }}</div>
      <div v-else-if="loadError" class="empty error-msg">✕ {{ loadError }}</div>
      <template v-else>
        <div v-if="config.chartType === 'bar'" style="margin-bottom:16px">
          <SimpleBarChart :rows="chartRows" />
        </div>
        <div v-else-if="config.chartType === 'pie'" style="margin-bottom:16px">
          <SimplePieChart :rows="chartRows" />
        </div>

        <table class="result-table">
          <thead>
            <tr>
              <th>{{ dimensionLabel(config.dimensions[0]) }}</th>
              <th v-if="secondDimension">{{ dimensionLabel(secondDimension) }}</th>
              <th>{{ metricLabel }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in results" :key="i">
              <td>{{ row.dim0 }}</td>
              <td v-if="secondDimension">{{ row.dim1 }}</td>
              <td class="num">{{ fmt(row.value) }}</td>
            </tr>
            <tr v-if="!results.length"><td :colspan="secondDimension ? 3 : 2" class="empty">{{ t('reportBuilder.result.noResultsForFilters') }}</td></tr>
          </tbody>
        </table>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'
import SimpleBarChart from './SimpleBarChart.vue'
import SimplePieChart from './SimplePieChart.vue'
import { sortCategoriesAsTree } from '../utils/categoryTree.js'

const { t } = useI18n()

const dimensionOptions = computed(() => [
  { value: 'category', label: t('reportBuilder.dimensions.category') },
  { value: 'account', label: t('reportBuilder.dimensions.account') },
  { value: 'person', label: t('reportBuilder.dimensions.person') },
  { value: 'destination', label: t('reportBuilder.dimensions.destination') },
  { value: 'month', label: t('reportBuilder.dimensions.month') },
  { value: 'day', label: t('reportBuilder.dimensions.day') },
  { value: 'merchant', label: t('reportBuilder.dimensions.merchant') },
])
function dimensionLabel(v) {
  return dimensionOptions.value.find(d => d.value === v)?.label || v
}

function emptyConfig() {
  return {
    dimensions: ['category'],
    metric: 'sum',
    absolute: true,
    chartType: 'bar',
    filters: {
      dateFrom: '', dateTo: '', accountId: '', categoryId: '', personId: '',
      destination: '', type: '', confirmedOnly: false,
    },
  }
}

const config = reactive(emptyConfig())
// Seconda dimensione tenuta separata perche' config.dimensions e' l'array che
// il backend consuma cosi' com'e' (max 2, ordine = ordine di raggruppamento):
// evita di dover ripulire '' dall'array ad ogni watch.
const secondDimension = ref('')
watch(secondDimension, v => {
  config.dimensions = v ? [config.dimensions[0], v] : [config.dimensions[0]]
})
watch(() => config.dimensions[0], v => {
  if (v === secondDimension.value) secondDimension.value = ''
  config.dimensions = secondDimension.value ? [v, secondDimension.value] : [v]
})

const accounts = ref([])
const categories = ref([])
// Esclude le categorie disattivate e quelle di sistema (es. 'Saldo iniziale',
// type='opening_balance', usata solo dal checkpoint annuale in Accounts.vue):
// non sono spese/entrate reali su cui filtrare un report.
const categoriesTree = computed(() => sortCategoriesAsTree(
  categories.value.filter(c => c.is_active && c.type !== 'opening_balance')
))
const persons = ref([])
const savedReports = ref([])
const selectedReportId = ref('')
const results = ref([])
const loading = ref(false)
const loadError = ref('')

const currentName = computed(() => savedReports.value.find(r => r.id === selectedReportId.value)?.name || '')
const metricLabel = computed(() => ({ sum: t('reportBuilder.metrics.sum'), count: t('reportBuilder.metrics.count'), avg: t('reportBuilder.metrics.avg') }[config.metric] || t('reportBuilder.metrics.value')))
const chartRows = computed(() => results.value.map(r => ({
  label: secondDimension.value ? `${r.dim0} · ${r.dim1}` : r.dim0,
  value: r.value,
})))

function fmt(v) {
  if (config.metric === 'count') return v
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v || 0)
}

function buildPayload() {
  const filters = {}
  for (const [k, v] of Object.entries(config.filters)) {
    if (v !== '' && v !== false) filters[k] = v
  }
  return { dimensions: config.dimensions, metric: config.metric, absolute: config.absolute, filters }
}

async function loadResults() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await api.post('api/reports/query', buildPayload())
    results.value = Array.isArray(res.data) ? res.data : []
  } catch (e) {
    loadError.value = e?.response?.data?.error || e?.response?.data?.detail || t('reportBuilder.errors.computeReport')
    results.value = []
  } finally {
    loading.value = false
  }
}

async function loadLookups() {
  const [a, c, p] = await Promise.all([
    api.get('api/accounts'),
    api.get('api/categories'),
    api.get('api/persons'),
  ])
  accounts.value = Array.isArray(a.data) ? a.data : []
  categories.value = Array.isArray(c.data) ? c.data : []
  persons.value = Array.isArray(p.data) ? p.data : []
}

async function loadSavedReports() {
  const res = await api.get('api/reports/custom')
  savedReports.value = Array.isArray(res.data) ? res.data : []
}

function applyConfig(saved) {
  Object.assign(config, emptyConfig(), saved, { filters: { ...emptyConfig().filters, ...(saved.filters || {}) } })
  secondDimension.value = config.dimensions[1] || ''
}

function onSelectSaved() {
  if (!selectedReportId.value) {
    applyConfig(emptyConfig())
    return
  }
  const saved = savedReports.value.find(r => r.id === selectedReportId.value)
  if (saved) applyConfig(saved.config)
}

async function saveAsNew() {
  const name = prompt(t('reportBuilder.prompts.reportName'))
  if (!name) return
  const res = await api.post('api/reports/custom', { name, config: JSON.parse(JSON.stringify(config)) })
  savedReports.value.unshift(res.data)
  selectedReportId.value = res.data.id
}

async function updateCurrent() {
  if (!selectedReportId.value) return
  const res = await api.put(`api/reports/custom/${selectedReportId.value}`, { config: JSON.parse(JSON.stringify(config)) })
  const idx = savedReports.value.findIndex(r => r.id === selectedReportId.value)
  if (idx !== -1) savedReports.value[idx] = res.data
}

async function deleteCurrent() {
  if (!selectedReportId.value) return
  if (!confirm(t('reportBuilder.prompts.confirmDelete', { name: currentName.value }))) return
  await api.delete(`api/reports/custom/${selectedReportId.value}`)
  savedReports.value = savedReports.value.filter(r => r.id !== selectedReportId.value)
  selectedReportId.value = ''
}

let debounceTimer = null
watch(config, () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(loadResults, 300)
}, { deep: true })

onMounted(async () => {
  await Promise.all([loadLookups(), loadSavedReports()])
  loadResults()
})
</script>

<style scoped>
.card { background:#fff; border:1px solid #DDD9D0; padding:20px; }
.card-title { font-size:13px; font-weight:600; margin-bottom:16px; }
.saved-row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.builder-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
.form-group { display:flex; flex-direction:column; gap:6px; }
.label { font-size:11px; color:#9A938C; text-transform:uppercase; letter-spacing:.02em; }
.input { padding:8px 11px; border:1px solid #DDD9D0; background:#F7F6F2; font-size:13px; font-family:inherit; outline:none; }
.input:focus { border-color:#1D3557; background:#fff; }
.check { display:flex; align-items:center; gap:6px; font-size:12px; }
.btn { display:inline-flex; align-items:center; padding:7px 14px; font-size:13px; cursor:pointer; border:1px solid #DDD9D0; background:#fff; color:#5C5752; }
.btn-sm { padding:5px 10px; font-size:12px; }
.btn-icon { border:1px solid #DDD9D0; background:#fff; width:28px; height:28px; display:inline-flex; align-items:center; justify-content:center; cursor:pointer; color:#5C5752; }
.btn-icon.danger:hover { color:#E76F51; border-color:#E76F51; }
.result-table { width:100%; border-collapse:collapse; font-size:12.5px; }
.result-table th { text-align:left; color:#9A938C; font-weight:500; padding:6px; border-bottom:1px solid #DDD9D0; }
.result-table th:last-child, .result-table td:last-child { text-align:right; }
.result-table td { padding:6px; border-bottom:1px solid #F0EEE9; }
.num { font-variant-numeric: tabular-nums; }
.empty { text-align:center; padding:24px; color:#9A938C; font-size:13px; }
.error-msg { color:#E76F51; }
</style>
