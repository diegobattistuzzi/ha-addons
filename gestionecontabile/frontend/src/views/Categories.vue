<template>
  <div>
    <div class="topbar">
      <div class="topbar-title">{{ t('categories.title') }}</div>
      <div class="topbar-actions">
        <div class="type-tabs">
          <button :class="['tab', tab==='expense' && 'active']" @click="tab='expense'">{{ t('categories.tabs.expense') }}</button>
          <button :class="['tab', tab==='income'  && 'active']" @click="tab='income'">{{ t('categories.tabs.income') }}</button>
          <button :class="['tab', tab==='transfer'&& 'active']" @click="tab='transfer'">{{ t('categories.tabs.transfer') }}</button>
        </div>
        <button class="btn btn-primary btn-sm" @click="openAdd">+ {{ t('common.add') }}</button>
      </div>
    </div>

    <div class="content">
      <div v-if="loading" class="empty">{{ t('common.loading') }}</div>
      <div v-else-if="error" class="empty err">{{ error }}</div>
      <div v-else-if="!filtered.length" class="empty">{{ t('categories.emptyState', { type: tab }) }}</div>

      <div v-else class="cat-table">
        <div class="cat-header">
          <div>{{ t('categories.headers.code') }}</div><div>{{ t('categories.headers.icon') }}</div><div>{{ t('common.name') }}</div><div>{{ t('categories.headers.monthlyBudget') }}</div><div>{{ t('categories.headers.annualBudget') }}</div><div>{{ t('categories.headers.aiKeywords') }}</div><div></div>
        </div>
        <div v-for="c in filtered" :key="c.id" class="cat-row" :class="{ inactive: !c.is_active, 'cat-child': c.depth }">
          <div class="cat-code">{{ c.code || '—' }}</div>
          <div class="cat-icon">{{ c.icon || '📌' }}</div>
          <div class="cat-name">{{ c.depth ? '↳ ' : '' }}{{ c.name }}</div>
          <div class="cat-budget">
            <span v-if="c.budget_monthly">{{ t('categories.perMonth', { amount: fmt(c.budget_monthly) }) }}</span>
            <span v-else class="muted">—</span>
          </div>
          <div class="cat-budget">
            <span v-if="c.budget_annual">{{ t('categories.perYear', { amount: fmt(c.budget_annual) }) }}</span>
            <span v-else class="muted">—</span>
          </div>
          <div class="cat-keywords">
            <span v-for="kw in keywords(c)" :key="kw" class="kw-chip">{{ kw }}</span>
          </div>
          <div class="cat-actions">
            <button class="btn-icon" @click="openEdit(c)" :title="t('common.edit')">✎</button>
            <button class="btn-icon" @click="toggle(c)" :title="c.is_active ? t('categories.deactivateTitle') : t('categories.reactivateTitle')">
              {{ c.is_active ? '⏻' : '↺' }}
            </button>
            <button class="btn-icon danger" @click="remove(c)" :title="t('categories.deleteTitle')">🗑</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal -->
    <div v-if="showModal" class="modal-backdrop" @click.self="showModal=false">
      <div class="modal">
        <div class="modal-header">
          <span>{{ editId ? t('categories.editTitle') : t('categories.newTitle') }}</span>
          <button class="btn-icon" @click="showModal=false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <div class="form-group">
              <label class="label">{{ t('categories.form.codeLabel') }}</label>
              <input class="input" v-model="form.code" :placeholder="t('categories.form.codePlaceholder')" style="text-transform:uppercase" />
            </div>
            <div class="form-group">
              <label class="label">{{ t('categories.form.iconLabel') }}</label>
              <input class="input" v-model="form.icon" placeholder="🛒" />
            </div>
          </div>
          <div class="form-group">
            <label class="label">{{ t('categories.form.nameLabel') }}</label>
            <input class="input" v-model="form.name" :placeholder="t('categories.form.namePlaceholder')" autofocus />
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="label">{{ t('common.type') }}</label>
              <select class="input" v-model="form.type">
                <option value="expense">{{ t('categories.typeOptions.expense') }}</option>
                <option value="income">{{ t('categories.typeOptions.income') }}</option>
                <option value="transfer">{{ t('categories.typeOptions.transfer') }}</option>
              </select>
            </div>
            <div class="form-group">
              <label class="label">{{ t('categories.form.monthlyBudgetLabel') }}</label>
              <input class="input" type="number" min="0" step="10" v-model="form.budgetMonthly" placeholder="—" />
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="label">{{ t('categories.form.annualBudgetLabel') }}</label>
              <input class="input" type="number" min="0" step="50" v-model="form.budgetAnnual" placeholder="—" />
              <div class="field-hint">{{ t('categories.form.annualBudgetHint') }}</div>
            </div>
            <div class="form-group">
              <label class="label">{{ t('categories.form.parentLabel') }}</label>
              <select class="input" v-model="form.parentId" :disabled="!parentCandidates.length && !form.parentId">
                <option value="">{{ t('categories.form.noParentOption') }}</option>
                <option v-for="p in parentCandidates" :key="p.id" :value="p.id">{{ p.name }}</option>
              </select>
              <div class="field-hint" v-if="hasOwnChildren">{{ t('categories.form.hasChildrenHint') }}</div>
            </div>
          </div>
          <div class="form-group">
            <label class="label">{{ t('categories.form.aiKeywordsLabel') }}</label>
            <input class="input" v-model="form.aiKeywordsRaw" :placeholder="t('categories.form.aiKeywordsPlaceholder')" />
            <div class="field-hint">{{ t('categories.form.aiKeywordsHint') }}</div>
          </div>
          <div v-if="formError" class="form-error">{{ formError }}</div>
        </div>
        <div class="modal-footer">
          <button class="btn" @click="showModal=false">{{ t('common.cancel') }}</button>
          <button class="btn btn-primary" @click="save" :disabled="saving">{{ saving ? '...' : t('common.save') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'
import { sortCategoriesAsTree } from '../utils/categoryTree.js'

const { t } = useI18n()

const categories = ref([])
const loading    = ref(true)
const error      = ref('')
const tab        = ref('expense')
const showModal  = ref(false)
const saving     = ref(false)
const formError  = ref('')
const editId     = ref(null)

const fmt = v => new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v)

const keywords = c => {
  try { return JSON.parse(c.ai_keywords || '[]').slice(0, 4) } catch { return [] }
}

// Gerarchia a 2 livelli (categoria -> sotto-categoria, vedi
// _validate_category_parent nel backend e utils/categoryTree.js): una
// categoria il cui genitore non e' piu' nello stesso elenco filtrato (es.
// disattivato/eliminato) viene trattata come radice, altrimenti sparirebbe.
const filtered = computed(() => sortCategoriesAsTree(
  categories.value.filter(c => c.type === tab.value && c.is_active !== false)
))

const emptyForm = () => ({ code: '', name: '', icon: '', type: tab.value, budgetMonthly: '', budgetAnnual: '', aiKeywordsRaw: '', parentId: '' })
const form = ref(emptyForm())

// Candidati come genitore: solo categorie di primo livello dello stesso tipo
// (niente sotto-categorie di sotto-categorie), esclusa la categoria che si sta
// modificando (non puo' essere genitore di se stessa).
const parentCandidates = computed(() =>
  categories.value.filter(c => c.type === form.value.type && !c.parent_id && c.id !== editId.value)
)
const hasOwnChildren = computed(() =>
  editId.value != null && categories.value.some(c => c.parent_id === editId.value)
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.get('api/categories')
    categories.value = res.data
  } catch (e) {
    error.value = e?.response?.data?.error || e.message
  } finally {
    loading.value = false
  }
}

function openAdd() {
  form.value = emptyForm()
  editId.value = null
  formError.value = ''
  showModal.value = true
}

function openEdit(c) {
  let kw = []
  try { kw = JSON.parse(c.ai_keywords || '[]') } catch {}
  form.value = {
    code: c.code || '',
    name: c.name,
    icon: c.icon || '',
    type: c.type,
    budgetMonthly: c.budget_monthly || '',
    budgetAnnual: c.budget_annual || '',
    aiKeywordsRaw: kw.join(', '),
    parentId: c.parent_id || '',
  }
  editId.value = c.id
  formError.value = ''
  showModal.value = true
}

async function save() {
  formError.value = ''
  if (!form.value.name.trim()) { formError.value = t('categories.nameRequired'); return }
  saving.value = true
  try {
    const kw = form.value.aiKeywordsRaw.split(',').map(k => k.trim()).filter(Boolean)
    const payload = {
      code:         form.value.code.toUpperCase() || null,
      name:         form.value.name,
      icon:         form.value.icon || null,
      type:         form.value.type,
      budgetMonthly: form.value.budgetMonthly !== '' ? Number(form.value.budgetMonthly) : null,
      budgetAnnual: form.value.budgetAnnual !== '' ? Number(form.value.budgetAnnual) : null,
      aiKeywords:   JSON.stringify(kw),
      parentId:     form.value.parentId || null,
    }
    if (editId.value) {
      await api.put(`api/categories/${editId.value}`, payload)
    } else {
      await api.post('api/categories', payload)
    }
    showModal.value = false
    load()
  } catch (e) {
    formError.value = e?.response?.data?.error || e.message
  } finally {
    saving.value = false
  }
}

async function toggle(c) {
  await api.put(`api/categories/${c.id}`, { isActive: !c.is_active })
  load()
}

async function remove(c) {
  if (!confirm(t('categories.deleteConfirm', { name: c.name }))) return
  try {
    await api.delete(`api/categories/${c.id}`)
    load()
  } catch (e) {
    alert(e?.response?.data?.error || t('categories.deleteError'))
  }
}

onMounted(load)
</script>

<style scoped>
.topbar { background:#fff; border-bottom:1px solid #DDD9D0; padding:0 28px; height:56px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10; }
.topbar-title { font-size:15px; font-weight:600; }
.topbar-actions { display:flex; align-items:center; gap:10px; }
.type-tabs { display:flex; gap:2px; }
.tab { padding:5px 12px; font-size:12px; border:1px solid #DDD9D0; background:#fff; cursor:pointer; color:#5C5752; }
.tab.active { background:#1D3557; color:#fff; border-color:#1D3557; }

.content { padding:28px; max-width:960px; }
.empty { text-align:center; padding:60px; color:#9A938C; font-size:13px; }
.err   { color:#E76F51; }

.cat-table { background:#fff; border:1px solid #DDD9D0; }
.cat-header { display:grid; grid-template-columns:60px 44px 1fr 110px 110px 1fr 96px; padding:10px 16px; background:#F0EEE9; font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:#9A938C; border-bottom:1px solid #DDD9D0; gap:12px; }
.cat-row    { display:grid; grid-template-columns:60px 44px 1fr 110px 110px 1fr 96px; padding:10px 16px; border-bottom:1px solid #DDD9D0; align-items:center; gap:12px; }
.cat-row:last-child { border-bottom:none; }
.cat-row:hover { background:#F7F6F2; }
.cat-row.inactive { opacity:.45; }
.cat-row.cat-child { background:#FBFAF8; }
.cat-row.cat-child .cat-name { padding-left:16px; color:#5C5752; font-weight:400; }
.cat-code    { font-size:12px; font-weight:700; color:#1D3557; font-family:monospace; }
.cat-icon    { font-size:18px; }
.cat-name    { font-size:13px; font-weight:500; }
.cat-budget  { font-size:12px; color:#5C5752; font-variant-numeric:tabular-nums; }
.cat-keywords { display:flex; flex-wrap:wrap; gap:3px; }
.cat-actions { display:flex; gap:4px; }
.kw-chip { font-size:10px; padding:2px 6px; background:#F0EEE9; color:#5C5752; }
.muted   { color:#DDD9D0; }

.btn { display:inline-flex; align-items:center; padding:7px 14px; font-size:13px; cursor:pointer; border:1px solid #DDD9D0; background:#fff; color:#5C5752; }
.btn:disabled { opacity:.5; cursor:not-allowed; }
.btn-primary { background:#1D3557; color:#fff; border-color:#1D3557; }
.btn-sm { padding:5px 10px; font-size:12px; }
.btn-icon { width:28px; height:28px; border:1px solid #DDD9D0; background:#fff; cursor:pointer; font-size:12px; display:grid; place-items:center; }
.btn-icon.danger:hover { background:#FCF0EC; border-color:#E76F51; color:#E76F51; }

.modal-backdrop { position:fixed; inset:0; background:rgba(0,0,0,.35); z-index:100; display:grid; place-items:center; }
.modal { background:#fff; width:520px; max-width:95vw; border:1px solid #DDD9D0; display:flex; flex-direction:column; }
.modal-header { padding:16px 20px; border-bottom:1px solid #DDD9D0; display:flex; justify-content:space-between; align-items:center; font-size:14px; font-weight:600; }
.modal-body   { padding:20px; display:flex; flex-direction:column; gap:14px; }
.modal-footer { padding:16px 20px; border-top:1px solid #DDD9D0; display:flex; justify-content:flex-end; gap:8px; }
.form-row  { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
.form-group { display:flex; flex-direction:column; gap:6px; }
.label { font-size:12px; font-weight:500; color:#5C5752; }
.input { padding:8px 11px; border:1px solid #DDD9D0; background:#F7F6F2; font-size:13px; font-family:inherit; outline:none; }
.input:focus { border-color:#1D3557; background:#fff; }
.field-hint { font-size:11px; color:#9A938C; }
.form-error { font-size:12px; color:#E76F51; }
</style>
