<template>
  <div>
    <div class="topbar">
      <div class="topbar-title">{{ t('rules.title') }}</div>
      <div class="topbar-actions">
        <button class="btn btn-primary btn-sm" @click="openAdd">+ {{ t('rules.addButton') }}</button>
      </div>
    </div>

    <div class="content">
      <div class="info-box">ℹ {{ t('rules.hint') }}</div>

      <div v-if="loading" class="empty">{{ t('common.loading') }}</div>
      <div v-else-if="error" class="empty error-msg">{{ error }}</div>
      <div v-else-if="!rules.length" class="empty">{{ t('rules.empty') }}</div>

      <div v-else class="rule-list">
        <div v-for="r in rules" :key="r.id" class="rule-card" :class="{ inactive: !r.is_active }">
          <div class="rule-main">
            <div class="rule-pattern">
              <span class="rule-mono">{{ r.pattern }}</span>
              <span v-if="r.is_regex" class="chip chip-regex">regex</span>
              <span v-if="r.sign" class="chip">{{ r.sign === 'negative' ? t('rules.form.signNegative') : t('rules.form.signPositive') }}</span>
            </div>
            <div class="rule-meta">
              {{ categoryLabel(r.category_id) }}
              <template v-if="r.destination"> · {{ destLabel(r.destination) }}</template>
              <template v-if="r.paid_by_person_id"> · {{ personName(r.paid_by_person_id) }}</template>
              <template v-if="r.destination === 'split' && r.split_person_id"> + {{ personName(r.split_person_id) }} ({{ Math.round((r.split_ratio ?? 0.5) * 100) }}/{{ 100 - Math.round((r.split_ratio ?? 0.5) * 100) }})</template>
            </div>
          </div>
          <div class="rule-right">
            <span class="rule-priority" :title="t('rules.form.priority')">{{ r.priority }}</span>
            <button class="btn-icon" @click="toggleActive(r)" :title="r.is_active ? t('rules.deactivate') : t('rules.activate')">{{ r.is_active ? '⏸' : '▶' }}</button>
            <button class="btn-icon" @click="openEdit(r)" :title="t('common.edit')">✎</button>
            <button class="btn-icon danger" @click="del(r)" :title="t('common.delete')">✕</button>
          </div>
        </div>
      </div>
    </div>

    <RuleFormModal v-if="showModal"
      :initial-rule="editRule"
      :categories="categories"
      :persons="persons"
      @saved="onSaved"
      @close="showModal = false"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'
import RuleFormModal from '../components/RuleFormModal.vue'

const { t } = useI18n()

const rules      = ref([])
const categories = ref([])
const persons    = ref([])
const loading    = ref(true)
const error      = ref('')
const showModal  = ref(false)
const editRule   = ref(null)

const categoryLabel = id => {
  const c = categories.value.find(x => x.id === id)
  return c ? `${c.icon} ${c.name}` : '—'
}
const personName = id => persons.value.find(p => p.id === id)?.name || '—'
const destLabel  = d => ({ family: t('transactions.destination.family'), personal: t('transactions.destination.personal'), split: t('transactions.destination.split') }[d] || d)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [rulesRes, catsRes, personsRes] = await Promise.all([
      api.get('api/rules'),
      api.get('api/categories'),
      api.get('api/persons'),
    ])
    rules.value = rulesRes.data
    categories.value = catsRes.data
    persons.value = personsRes.data
  } catch (e) {
    error.value = e?.response?.data?.detail || e.message || t('rules.errors.loadFailed')
  } finally {
    loading.value = false
  }
}

function openAdd() {
  editRule.value = null
  showModal.value = true
}

function openEdit(r) {
  editRule.value = {
    id: r.id,
    pattern: r.pattern,
    isRegex: !!r.is_regex,
    sign: r.sign || '',
    categoryId: r.category_id,
    destination: r.destination || '',
    paidByPersonId: r.paid_by_person_id || '',
    splitPersonId: r.split_person_id || '',
    splitRatio: r.split_ratio,
    priority: r.priority,
    isActive: !!r.is_active,
  }
  showModal.value = true
}

function onSaved() {
  showModal.value = false
  load()
}

async function toggleActive(r) {
  await api.put(`api/rules/${r.id}`, { isActive: !r.is_active })
  load()
}

async function del(r) {
  if (!confirm(t('rules.confirmDelete', { pattern: r.pattern }))) return
  try {
    await api.delete(`api/rules/${r.id}`)
    load()
  } catch (e) {
    alert(e?.response?.data?.detail || t('rules.errors.saveFailed'))
  }
}

onMounted(load)
</script>

<style scoped>
.topbar { background:#fff; border-bottom:1px solid #DDD9D0; padding:0 28px; height:56px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10; }
.topbar-title { font-size:15px; font-weight:600; }
.topbar-actions { display:flex; gap:8px; }
.content { padding:28px; max-width:900px; }
.info-box { margin-bottom:20px; padding:12px 16px; background:#EBF0F6; border:1px solid #1D3557; font-size:12px; color:#1D3557; line-height:1.6; }
.empty { text-align:center; padding:60px; color:#9A938C; font-size:13px; }
.error-msg { color:#E76F51; }

.rule-list { display:flex; flex-direction:column; gap:8px; }
.rule-card { background:#fff; border:1px solid #DDD9D0; padding:14px 18px; display:flex; align-items:center; justify-content:space-between; gap:16px; }
.rule-card.inactive { opacity:.5; }
.rule-main { display:flex; flex-direction:column; gap:4px; min-width:0; }
.rule-pattern { display:flex; align-items:center; gap:8px; font-size:13.5px; }
.rule-mono { font-family:monospace; background:#F7F6F2; padding:2px 6px; }
.rule-meta { font-size:12px; color:#9A938C; }
.rule-right { display:flex; align-items:center; gap:6px; flex-shrink:0; }
.rule-priority { font-size:11px; color:#9A938C; min-width:18px; text-align:center; }
.chip { font-size:10.5px; padding:2px 6px; background:#F0EEE9; color:#5C5752; border-radius:2px; }
.chip-regex { background:#EBF0F6; color:#1D3557; }

.btn { display:inline-flex; align-items:center; gap:6px; padding:7px 14px; font-size:13px; cursor:pointer; border:1px solid #DDD9D0; background:#fff; color:#5C5752; }
.btn-primary { background:#1D3557; color:#fff; border-color:#1D3557; }
.btn-sm { padding:5px 10px; font-size:12px; }
.btn-icon { width:28px; height:28px; border:1px solid #DDD9D0; background:#fff; cursor:pointer; font-size:12px; display:grid; place-items:center; }
.btn-icon.danger:hover { background:#FCF0EC; border-color:#E76F51; color:#E76F51; }
</style>
