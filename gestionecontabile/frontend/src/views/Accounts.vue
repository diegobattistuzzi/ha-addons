<template>
  <div>
    <div class="topbar">
      <div class="topbar-title">{{ t('accounts.title') }}</div>
      <div class="topbar-actions">
        <button class="btn btn-primary btn-sm" @click="openAdd">+ {{ t('accounts.addButton') }}</button>
      </div>
    </div>

    <div class="content">
      <div v-if="loading" class="empty">{{ t('common.loading') }}</div>
      <div v-else-if="error" class="empty error-msg">{{ error }}</div>
      <div v-else-if="!accounts.length" class="empty">
        {{ t('accounts.empty') }}
      </div>

      <div v-else class="account-list">
        <div v-for="a in accounts" :key="a.id" class="account-card">
          <div class="account-left">
            <div class="account-bank-logo">{{ a.type === 'meal_voucher' ? '🍽️' : bankEmoji(a.bank) }}</div>
            <div>
              <div class="account-name">{{ a.name }}</div>
              <div class="account-meta">
                {{ bankLabel(a.bank) }} · {{ typeLabel(a.type) }} ·
                <span :class="`own-${a.ownership}`">{{ ownerLabel(a.ownership) }}</span>
                <span v-if="a.ownership === 'personal'">· {{ personName(a.owner_id) }}</span>
              </div>
              <div v-if="a.iban" class="account-iban">{{ a.iban }}</div>
              <div v-if="a.settlement_account_id" class="account-settlement">{{ t('accounts.settlementLabel', { name: accountName(a.settlement_account_id) }) }}</div>
            </div>
          </div>
          <div class="account-right">
            <div class="account-balance" :class="(a.balance||0) >= 0 ? 'pos' : 'neg'">
              {{ fmt(a.balance || 0) }}
            </div>
            <div class="account-actions">
              <button class="btn-icon" @click="openBalanceModal(a)" :title="t('accounts.openingBalance.buttonTitle')">🏁</button>
              <button class="btn-icon" @click="openEdit(a)">✎</button>
              <button class="btn-icon danger" @click="del(a)">✕</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal add/edit -->
    <div v-if="showModal" class="modal-backdrop" @click.self="showModal=false">
      <div class="modal">
        <div class="modal-header">
          <span>{{ editId ? t('accounts.modal.editTitle') : t('accounts.modal.addTitle') }}</span>
          <button class="btn-icon" @click="showModal=false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <div class="form-group">
              <label class="label">{{ t('accounts.form.name') }}</label>
              <input class="input" v-model="form.name" :placeholder="t('accounts.form.namePlaceholder')" autofocus />
            </div>
            <div class="form-group">
              <label class="label">{{ t('accounts.form.bank') }}</label>
              <select class="input" v-model="form.bank">
                <option v-for="b in banks" :key="b.value" :value="b.value">{{ b.label }}</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="label">{{ t('accounts.form.type') }}</label>
              <select class="input" v-model="form.type">
                <option value="checking">{{ t('accounts.types.checking') }}</option>
                <option value="credit_card">{{ t('accounts.types.creditCard') }}</option>
                <option value="savings">{{ t('accounts.types.savings') }}</option>
                <option value="cash">{{ t('accounts.types.cash') }}</option>
                <option value="meal_voucher">{{ t('accounts.types.mealVoucher') }}</option>
              </select>
            </div>
            <div class="form-group">
              <label class="label">{{ t('accounts.form.ownership') }}</label>
              <select class="input" v-model="form.ownership">
                <option value="shared">{{ t('accounts.ownership.shared') }}</option>
                <option value="personal">{{ t('accounts.ownership.personal') }}</option>
              </select>
            </div>
          </div>
          <div v-if="form.ownership === 'personal'" class="form-group">
            <label class="label">{{ t('accounts.form.owner') }}</label>
            <select class="input" v-model="form.ownerId">
              <option value="" disabled>{{ t('accounts.form.choosePerson') }}</option>
              <option v-for="p in persons" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </div>
          <div v-if="form.ownership === 'personal' && coOwnerCandidates.length" class="form-group">
            <label class="label">{{ t('accounts.form.coOwners') }}</label>
            <div class="co-owners-list">
              <label v-for="p in coOwnerCandidates" :key="p.id" class="co-owner-item">
                <input type="checkbox" :value="p.id" v-model="form.coOwners" />
                {{ p.name }}
              </label>
            </div>
            <div class="field-hint">{{ t('accounts.form.coOwnersHint') }}</div>
          </div>
          <div v-if="form.type === 'credit_card'" class="form-group">
            <label class="label">{{ t('accounts.form.settlementAccount') }}</label>
            <select class="input" v-model="form.settlementAccountId">
              <option value="">{{ t('accounts.form.none') }}</option>
              <option v-for="a in settlementCandidates" :key="a.id" :value="a.id">{{ a.name }}</option>
            </select>
            <div class="field-hint">{{ t('accounts.form.settlementHint') }}</div>
          </div>
          <div v-if="form.type === 'credit_card'" class="form-group">
            <label class="label">{{ t('accounts.form.cardNumber') }}</label>
            <input class="input" v-model="form.cardNumber" :placeholder="t('accounts.form.cardNumberPlaceholder')" />
            <div class="field-hint">{{ t('accounts.form.cardNumberHint') }}</div>
          </div>
          <div v-if="form.type === 'credit_card'" class="form-group">
            <label class="label">{{ t('accounts.form.amountSignMode') }}</label>
            <select class="input" v-model="form.amountSignMode">
              <option value="auto">{{ t('accounts.form.amountSignModeAuto') }}</option>
              <option value="flip">{{ t('accounts.form.amountSignModeFlip') }}</option>
              <option value="signed">{{ t('accounts.form.amountSignModeSigned') }}</option>
            </select>
            <div class="field-hint">{{ t('accounts.form.amountSignModeHint') }}</div>
          </div>
          <div class="form-group">
            <label class="label">{{ t('accounts.form.iban') }}</label>
            <input class="input" v-model="form.iban" :placeholder="t('accounts.form.ibanPlaceholder')" />
          </div>
          <div v-if="formError" class="form-error">{{ formError }}</div>
        </div>
        <div class="modal-footer">
          <button class="btn" @click="showModal=false">{{ t('common.cancel') }}</button>
          <button class="btn btn-primary" @click="save" :disabled="saving">
            {{ saving ? '...' : t('common.save') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Modal saldo iniziale -->
    <div v-if="showBalanceModal" class="modal-backdrop" @click.self="showBalanceModal=false">
      <div class="modal">
        <div class="modal-header">
          <span>{{ t('accounts.openingBalance.title', { name: balanceAccount?.name }) }}</span>
          <button class="btn-icon" @click="showBalanceModal=false">✕</button>
        </div>
        <div class="modal-body">
          <div v-if="balanceCheckpoints.length" class="checkpoint-list">
            <div v-for="cp in balanceCheckpoints" :key="cp.id" class="checkpoint-row">
              <span class="checkpoint-date">{{ cp.date }}</span>
              <span class="num">{{ fmt(cp.amount) }}</span>
              <button class="btn-icon" @click="editCheckpoint(cp)" :title="t('common.edit')">✎</button>
              <button class="btn-icon danger" @click="deleteCheckpoint(cp)" :title="t('common.delete')">✕</button>
            </div>
          </div>
          <div v-else class="field-hint">{{ t('accounts.openingBalance.empty') }}</div>

          <div class="form-row" style="margin-top:12px">
            <div class="form-group">
              <label class="label">{{ t('accounts.openingBalance.dateLabel') }}</label>
              <input class="input" type="date" v-model="balanceForm.date" />
            </div>
            <div class="form-group">
              <label class="label">{{ t('accounts.openingBalance.amountLabel') }}</label>
              <input class="input" type="number" step="0.01" v-model="balanceForm.amount" placeholder="0.00" />
            </div>
          </div>
          <div class="field-hint">{{ t('accounts.openingBalance.hint') }}</div>
          <div v-if="balanceError" class="form-error">{{ balanceError }}</div>
        </div>
        <div class="modal-footer">
          <button class="btn" @click="showBalanceModal=false">{{ t('common.close') }}</button>
          <button class="btn btn-primary" @click="saveBalanceCheckpoint" :disabled="balanceSaving">
            {{ balanceSaving ? '...' : t('accounts.openingBalance.save') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'

const { t } = useI18n()

const accounts  = ref([])
const persons   = ref([])
const loading   = ref(true)
const error     = ref('')
const showModal = ref(false)
const saving    = ref(false)
const formError = ref('')
const editId    = ref(null)

const banks = computed(() => [
  { value:'fineco',    label:t('accounts.banks.fineco') },
  { value:'ing',       label:t('accounts.banks.ing') },
  { value:'n26',       label:t('accounts.banks.n26') },
  { value:'revolut',   label:t('accounts.banks.revolut') },
  { value:'wise',      label:t('accounts.banks.wise') },
  { value:'hellobank', label:t('accounts.banks.hellobank') },
  { value:'cash',      label:t('accounts.banks.cash') },
  { value:'other',     label:t('accounts.banks.other') },
])

const bankEmoji  = b => ({ fineco:'🏦', ing:'🧡', n26:'🖤', revolut:'🌐', wise:'💚', hellobank:'💙', cash:'💵', other:'🏧' })[b] || '🏧'
const bankLabel  = b => banks.value.find(x => x.value === b)?.label || b
const typeLabel  = ty => ({ checking:t('accounts.typeShort.checking'), credit_card:t('accounts.typeShort.creditCard'), savings:t('accounts.typeShort.savings'), cash:t('accounts.typeShort.cash'), meal_voucher:t('accounts.typeShort.mealVoucher') })[ty] || ty
const ownerLabel = o => ({ shared:t('accounts.ownership.shared'), personal:t('accounts.ownership.personal') })[o] || o
const personName  = id => persons.value.find(p => p.id === id)?.name || '—'
const accountName = id => accounts.value.find(a => a.id === id)?.name || '—'
const fmt = v => new Intl.NumberFormat('it-IT', { style:'currency', currency:'EUR' }).format(v)

const emptyForm = () => ({ name:'', bank:'other', type:'checking', ownership:'shared', ownerId:'', coOwners:[], settlementAccountId:'', iban:'', amountSignMode:'auto' })
const form = ref(emptyForm())

// Chi puo' essere aggiunto come co-titolare di un conto personale: tutti
// tranne il proprietario stesso (che vede il conto comunque).
const coOwnerCandidates = computed(() => persons.value.filter(p => p.id !== form.value.ownerId))

const showBalanceModal   = ref(false)
const balanceAccount     = ref(null)
const balanceCheckpoints = ref([])
const balanceSaving      = ref(false)
const balanceError       = ref('')
const emptyBalanceForm   = () => ({ date: new Date().toISOString().slice(0,10), amount: '' })
const balanceForm        = ref(emptyBalanceForm())

const settlementCandidates = computed(() =>
  accounts.value.filter(a => a.type !== 'credit_card' && a.type !== 'meal_voucher' && a.id !== editId.value)
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [accountsRes, personsRes] = await Promise.all([
      api.get('api/accounts'),
      api.get('api/persons'),
    ])
    accounts.value = accountsRes.data
    persons.value = personsRes.data
  } catch (e) {
    error.value = e?.response?.data?.error || e.message || t('accounts.errors.loadFailed')
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

function openEdit(a) {
  let coOwners = []
  try { coOwners = a.co_owners ? JSON.parse(a.co_owners) : [] } catch { coOwners = [] }
  form.value = { name:a.name, bank:a.bank||'other', type:a.type||'checking', ownership:a.ownership||'shared', ownerId:a.owner_id||'', coOwners, settlementAccountId:a.settlement_account_id||'', iban:a.iban||'', cardNumber:a.card_number||'', amountSignMode:a.amount_sign_mode||'auto' }
  editId.value = a.id
  formError.value = ''
  showModal.value = true
}

async function openBalanceModal(a) {
  balanceAccount.value = a
  balanceForm.value = emptyBalanceForm()
  balanceError.value = ''
  showBalanceModal.value = true
  await loadBalanceCheckpoints()
}

async function loadBalanceCheckpoints() {
  const res = await api.get(`api/accounts/${balanceAccount.value.id}/opening-balance`)
  balanceCheckpoints.value = Array.isArray(res.data) ? res.data : []
}

function editCheckpoint(cp) {
  balanceForm.value = { date: cp.date, amount: cp.amount }
}

async function saveBalanceCheckpoint() {
  if (!balanceForm.value.date || balanceForm.value.amount === '') return
  balanceSaving.value = true
  balanceError.value = ''
  try {
    await api.post(`api/accounts/${balanceAccount.value.id}/opening-balance`, {
      date: balanceForm.value.date,
      amount: Number(balanceForm.value.amount),
    })
    balanceForm.value = emptyBalanceForm()
    await loadBalanceCheckpoints()
    load()
  } catch (e) {
    balanceError.value = e?.response?.data?.error || t('accounts.errors.generic')
  } finally {
    balanceSaving.value = false
  }
}

async function deleteCheckpoint(cp) {
  if (!confirm(t('accounts.openingBalance.confirmDelete'))) return
  await api.delete(`api/transactions/${cp.id}`)
  await loadBalanceCheckpoints()
  load()
}

async function save() {
  formError.value = ''
  if (!form.value.name.trim()) { formError.value = t('accounts.errors.nameRequired'); return }
  if (form.value.ownership === 'personal' && !form.value.ownerId) { formError.value = t('accounts.errors.ownerRequired'); return }
  saving.value = true
  try {
    const payload = {
      ...form.value,
      ownerId: form.value.ownership === 'personal' ? form.value.ownerId : null,
      coOwners: form.value.ownership === 'personal' ? form.value.coOwners : null,
      settlementAccountId: form.value.type === 'credit_card' ? (form.value.settlementAccountId || null) : null,
      amountSignMode: form.value.type === 'credit_card' ? form.value.amountSignMode : 'auto',
    }
    if (editId.value) {
      await api.put(`api/accounts/${editId.value}`, payload)
    } else {
      await api.post('api/accounts', payload)
    }
    showModal.value = false
    load()
  } catch (e) {
    formError.value = e?.response?.data?.error || e.message || t('accounts.errors.saveFailed')
  } finally {
    saving.value = false
  }
}

async function del(a) {
  if (!confirm(t('accounts.confirmDeactivate', { name: a.name }))) return
  try {
    await api.delete(`api/accounts/${a.id}`)
    load()
  } catch (e) {
    alert(e?.response?.data?.error || t('accounts.errors.generic'))
  }
}

onMounted(load)
</script>

<style scoped>
.topbar { background:#fff; border-bottom:1px solid #DDD9D0; padding:0 28px; height:56px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10; }
.topbar-title { font-size:15px; font-weight:600; }
.topbar-actions { display:flex; gap:8px; }

.content { padding:28px; max-width:860px; }
.empty { text-align:center; padding:60px; color:#9A938C; font-size:13px; }
.error-msg { color:#E76F51; }

.account-list { display:flex; flex-direction:column; gap:8px; }
.account-card { background:#fff; border:1px solid #DDD9D0; padding:16px 20px; display:flex; align-items:center; justify-content:space-between; gap:16px; }
.account-left  { display:flex; align-items:center; gap:14px; }
.account-bank-logo { font-size:24px; width:40px; text-align:center; flex-shrink:0; }
.account-name  { font-size:14px; font-weight:600; }
.account-meta  { font-size:12px; color:#9A938C; margin-top:3px; }
.account-iban  { font-size:11px; color:#9A938C; font-family:monospace; margin-top:2px; }
.account-settlement { font-size:11px; color:#9A938C; margin-top:2px; }
.own-shared   { color:#2A9D8F; }
.own-personal { color:#E8A020; }
.account-right { display:flex; align-items:center; gap:12px; flex-shrink:0; }
.account-balance { font-size:16px; font-weight:600; font-variant-numeric:tabular-nums; }
.account-balance.pos { color:#2A9D8F; }
.account-balance.neg { color:#E76F51; }
.account-actions { display:flex; gap:4px; }

.btn { display:inline-flex; align-items:center; gap:6px; padding:7px 14px; font-size:13px; cursor:pointer; border:1px solid #DDD9D0; background:#fff; color:#5C5752; }
.btn:disabled { opacity:.5; cursor:not-allowed; }
.btn-primary { background:#1D3557; color:#fff; border-color:#1D3557; }
.btn-sm { padding:5px 10px; font-size:12px; }
.btn-icon { width:28px; height:28px; border:1px solid #DDD9D0; background:#fff; cursor:pointer; font-size:12px; display:grid; place-items:center; }
.btn-icon.danger:hover { background:#FCF0EC; border-color:#E76F51; color:#E76F51; }

.modal-backdrop { position:fixed; inset:0; background:rgba(0,0,0,.35); z-index:100; display:grid; place-items:center; }
.modal { background:#fff; width:480px; max-width:95vw; border:1px solid #DDD9D0; display:flex; flex-direction:column; }
.modal-header { padding:16px 20px; border-bottom:1px solid #DDD9D0; display:flex; justify-content:space-between; align-items:center; font-size:14px; font-weight:600; }
.modal-body   { padding:20px; display:flex; flex-direction:column; gap:14px; }
.modal-footer { padding:16px 20px; border-top:1px solid #DDD9D0; display:flex; justify-content:flex-end; gap:8px; }
.form-row  { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
.form-group { display:flex; flex-direction:column; gap:6px; }
.label { font-size:12px; font-weight:500; color:#5C5752; }
.input { padding:8px 11px; border:1px solid #DDD9D0; background:#F7F6F2; font-size:13px; font-family:inherit; outline:none; }
.input:focus { border-color:#1D3557; background:#fff; }
.form-error { font-size:12px; color:#E76F51; }
.field-hint { font-size:11px; color:#9A938C; line-height:1.4; }
.co-owners-list { display:flex; flex-direction:column; gap:6px; }
.co-owner-item { display:flex; align-items:center; gap:8px; font-size:13px; cursor:pointer; }
.checkpoint-list { display:flex; flex-direction:column; gap:2px; }
.checkpoint-row { display:flex; align-items:center; gap:10px; font-size:13px; padding:6px 0; border-bottom:1px solid #F0EEE9; }
.checkpoint-date { flex:1; }
.checkpoint-row .num { font-variant-numeric:tabular-nums; }
</style>
