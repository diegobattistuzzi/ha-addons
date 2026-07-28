<template>
  <div class="mtx">
    <div class="topbar">
      <div class="topbar-title">{{ t('mobile.transactions.title') }}</div>
      <input class="input" type="month" v-model="month" @change="load" />
    </div>

    <div v-if="loading" class="empty">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="empty error-msg">{{ error }}</div>
    <div v-else-if="!transactions.length" class="empty">{{ t('mobile.transactions.empty') }}</div>

    <div v-else class="list">
      <div v-for="tx in transactions" :key="tx.id" class="row" @click="openEdit(tx)">
        <div class="row-main">
          <div class="row-title">{{ tx.merchant_name || tx.description_raw || t('mobile.transactions.noDescription') }}</div>
          <div class="row-meta">
            {{ formatDay(tx.date) }} · {{ accountName(tx.account_id) }}
            <template v-if="tx.is_cash"> · 💵</template>
          </div>
        </div>
        <div class="row-amount" :class="{ negative: tx.amount < 0 }">{{ fmt(tx.amount) }}</div>
      </div>
    </div>

    <!-- Modal modifica -->
    <div v-if="editing" class="modal-backdrop" @click.self="editing = null">
      <div class="modal">
        <div class="modal-header">
          <span>{{ t('mobile.transactions.editTitle') }}</span>
          <button class="btn-icon" @click="editing = null">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="label">{{ t('mobile.scan.amountLabel') }}</label>
            <input class="input" type="number" step="0.01" v-model="editForm.amount" />
          </div>
          <div class="form-group">
            <label class="label">{{ t('mobile.scan.merchantLabel') }}</label>
            <input class="input" v-model="editForm.description" />
          </div>
          <div class="form-group">
            <label class="label">{{ t('mobile.scan.dateLabel') }}</label>
            <input class="input" type="date" v-model="editForm.date" />
          </div>
          <div class="form-group">
            <label class="label">{{ t('mobile.scan.categoryLabel') }}</label>
            <select class="input" v-model="editForm.categoryId">
              <option value="">{{ t('mobile.scan.categoryNone') }}</option>
              <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.icon }} {{ c.name }}</option>
            </select>
          </div>
          <div class="form-group">
            <label class="label">{{ t('mobile.scan.accountLabel') }}</label>
            <select class="input" v-model="editForm.accountId">
              <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.type === 'cash' ? '💵 ' : '' }}{{ a.name }}</option>
            </select>
          </div>
          <div v-if="editError" class="empty error-msg">{{ editError }}</div>
        </div>
        <div class="modal-footer">
          <button class="btn-icon danger" :title="t('mobile.transactions.deleteTitle')" @click="remove">🗑</button>
          <div class="spacer" />
          <button class="btn" @click="editing = null">{{ t('common.cancel') }}</button>
          <button class="btn btn-primary" @click="save" :disabled="saving">
            {{ saving ? '...' : t('common.save') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'

const { t } = useI18n()

const transactions = ref([])
const accounts = ref([])
const categories = ref([])
const loading = ref(true)
const error = ref('')
const month = ref(new Date().toISOString().slice(0, 7))

const editing = ref(null)
const editForm = ref({ amount: '', description: '', date: '', categoryId: '', accountId: '' })
const editError = ref('')
const saving = ref(false)

function fmt(amount) {
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(amount)
}

function formatDay(value) {
  if (!value) return '—'
  return new Date(value + 'T00:00:00').toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' })
}

function accountName(accountId) {
  const acc = accounts.value.find(a => a.id === accountId)
  return acc ? acc.name : '—'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [txRes, accountsRes, categoriesRes] = await Promise.all([
      api.get('api/transactions', { params: { month: month.value, limit: 100 } }),
      api.get('api/accounts'),
      api.get('api/categories'),
    ])
    transactions.value = txRes.data
    accounts.value = accountsRes.data
    categories.value = categoriesRes.data.filter(c => c.is_active && c.type === 'expense')
  } catch (e) {
    error.value = e?.response?.data?.detail || t('mobile.transactions.loadError')
  } finally {
    loading.value = false
  }
}

function openEdit(tx) {
  editing.value = tx
  editError.value = ''
  editForm.value = {
    amount: tx.amount,
    description: tx.description_raw || '',
    date: tx.date,
    categoryId: tx.category_id || '',
    accountId: tx.account_id,
  }
}

async function save() {
  saving.value = true
  editError.value = ''
  try {
    await api.put(`api/transactions/${editing.value.id}`, {
      amount: editForm.value.amount,
      description: editForm.value.description,
      date: editForm.value.date,
      categoryId: editForm.value.categoryId || null,
      accountId: editForm.value.accountId,
    })
    editing.value = null
    load()
  } catch (e) {
    editError.value = e?.response?.data?.detail || t('mobile.transactions.saveError')
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (!confirm(t('mobile.transactions.deleteConfirm'))) return
  try {
    await api.delete(`api/transactions/${editing.value.id}`)
    editing.value = null
    load()
  } catch (e) {
    editError.value = e?.response?.data?.detail || t('mobile.transactions.deleteError')
  }
}

onMounted(load)
</script>

<style scoped>
.mtx { min-height: 100%; }
.topbar { background:#fff; border-bottom:1px solid #DDD9D0; padding:14px 20px; position:sticky; top:0; z-index:10; display:flex; justify-content:space-between; align-items:center; gap:10px; }
.topbar-title { font-size:16px; font-weight:600; }
.topbar .input { padding:6px 8px; font-size:13px; }

.empty { text-align:center; padding:40px 20px; color:#9A938C; font-size:13px; }
.error-msg { color:#E76F51; }

.list { display:flex; flex-direction:column; }
.row { display:flex; justify-content:space-between; align-items:center; gap:10px; padding:14px 20px; background:#fff; border-bottom:1px solid #EEEAE3; cursor:pointer; }
.row-main { min-width:0; }
.row-title { font-size:14px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.row-meta { font-size:12px; color:#9A938C; margin-top:2px; }
.row-amount { font-size:14px; font-weight:700; color:#2A9D8F; white-space:nowrap; }
.row-amount.negative { color:#E76F51; }

.input { padding:8px 11px; border:1px solid #DDD9D0; background:#F7F6F2; font-size:14px; font-family:inherit; outline:none; }
.input:focus { border-color:#1D3557; background:#fff; }

.modal-backdrop { position:fixed; inset:0; background:rgba(0,0,0,.35); z-index:100; display:grid; place-items:center; }
.modal { background:#fff; width:420px; max-width:95vw; max-height:90vh; overflow-y:auto; border:1px solid #DDD9D0; display:flex; flex-direction:column; }
.modal-header { padding:16px 20px; border-bottom:1px solid #DDD9D0; display:flex; justify-content:space-between; align-items:center; font-size:14px; font-weight:600; }
.modal-body { padding:20px; display:flex; flex-direction:column; gap:14px; }
.modal-footer { padding:16px 20px; border-top:1px solid #DDD9D0; display:flex; align-items:center; gap:8px; }
.spacer { flex:1; }
.form-group { display:flex; flex-direction:column; gap:6px; }
.label { font-size:12px; font-weight:500; color:#5C5752; }

.btn { display:inline-flex; align-items:center; gap:6px; padding:7px 14px; font-size:13px; cursor:pointer; border:1px solid #DDD9D0; background:#fff; color:#5C5752; }
.btn:disabled { opacity:.5; cursor:not-allowed; }
.btn-primary { background:#1D3557; color:#fff; border-color:#1D3557; }
.btn-icon { width:32px; height:32px; border:1px solid #DDD9D0; background:#fff; cursor:pointer; font-size:14px; display:grid; place-items:center; }
.btn-icon.danger:hover { background:#FCF0EC; border-color:#E76F51; color:#E76F51; }
</style>
