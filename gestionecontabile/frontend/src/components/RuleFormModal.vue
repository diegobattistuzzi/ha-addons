<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-header">
        <span>{{ initialRule?.id ? t('rules.modal.editTitle') : t('rules.modal.addTitle') }}</span>
        <button class="btn-icon" @click="$emit('close')">✕</button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label class="label">{{ t('rules.form.pattern') }} *</label>
          <input class="input" v-model="form.pattern" :placeholder="t('rules.form.patternPlaceholder')" autofocus />
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="check"><input type="checkbox" v-model="form.isRegex" /> {{ t('rules.form.isRegex') }}</label>
            <div class="field-hint">{{ t('rules.form.isRegexHint') }}</div>
          </div>
          <div class="form-group">
            <label class="label">{{ t('rules.form.sign') }}</label>
            <select class="input" v-model="form.sign">
              <option value="">{{ t('rules.form.signAny') }}</option>
              <option value="negative">{{ t('rules.form.signNegative') }}</option>
              <option value="positive">{{ t('rules.form.signPositive') }}</option>
            </select>
          </div>
        </div>
        <div class="form-group">
          <label class="label">{{ t('common.category') }} *</label>
          <CategoryPicker v-model="form.categoryId" :categories="categories" />
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="label">{{ t('rules.form.destination') }}</label>
            <select class="input" v-model="form.destination">
              <option value="">{{ t('rules.form.destinationUnchanged') }}</option>
              <option value="family">{{ t('transactions.destination.family') }}</option>
              <option value="personal">{{ t('transactions.destination.personal') }}</option>
              <option value="split">{{ t('transactions.destination.split') }}</option>
            </select>
          </div>
          <div class="form-group">
            <label class="label">{{ t('rules.form.paidBy') }}</label>
            <select class="input" v-model="form.paidByPersonId">
              <option value="">{{ t('rules.form.paidByUnchanged') }}</option>
              <option v-for="p in persons" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </div>
        </div>
        <div v-if="form.destination === 'split'" class="form-row">
          <div class="form-group">
            <label class="label">{{ t('transactions.manualModal.splitWithLabel') }}</label>
            <select class="input" v-model="form.splitPersonId">
              <option value="">{{ t('transactions.manualModal.choosePerson') }}</option>
              <option v-for="p in persons" :key="p.id" :value="p.id" :disabled="p.id === form.paidByPersonId">{{ p.name }}</option>
            </select>
          </div>
          <div class="form-group">
            <label class="label">{{ t('transactions.manualModal.splitPercentLabel') }}</label>
            <input class="input" type="number" min="0" max="100" step="5" v-model="form.splitPercent" placeholder="50" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="label">{{ t('rules.form.priority') }}</label>
            <input class="input" type="number" v-model="form.priority" placeholder="0" />
            <div class="field-hint">{{ t('rules.form.priorityHint') }}</div>
          </div>
          <div class="form-group" style="justify-content:flex-end; padding-top:24px;">
            <label class="check"><input type="checkbox" v-model="form.isActive" /> {{ t('rules.form.isActive') }}</label>
          </div>
        </div>
        <div v-if="formError" class="form-error">{{ formError }}</div>
      </div>
      <div class="modal-footer">
        <button class="btn" @click="$emit('close')">{{ t('common.cancel') }}</button>
        <button class="btn btn-primary" @click="save" :disabled="saving">{{ saving ? '...' : t('common.save') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'
import CategoryPicker from './CategoryPicker.vue'

const { t } = useI18n()

const props = defineProps({
  initialRule: { type: Object, default: null },
  categories: { type: Array, required: true },
  persons: { type: Array, required: true },
})
const emit = defineEmits(['saved', 'close'])

const emptyForm = () => ({
  pattern: '', isRegex: false, sign: '', categoryId: '', destination: '',
  paidByPersonId: '', splitPersonId: '', splitPercent: 50, priority: 0, isActive: true,
})

function fromInitial(r) {
  if (!r) return emptyForm()
  return {
    pattern: r.pattern || '',
    isRegex: !!r.isRegex,
    sign: r.sign || '',
    categoryId: r.categoryId || '',
    destination: r.destination || '',
    paidByPersonId: r.paidByPersonId || '',
    splitPersonId: r.splitPersonId || '',
    splitPercent: r.splitRatio != null ? Math.round(r.splitRatio * 100) : 50,
    priority: r.priority || 0,
    isActive: r.isActive !== false,
  }
}

const form = ref(fromInitial(props.initialRule))
const saving = ref(false)
const formError = ref('')

async function save() {
  formError.value = ''
  if (!form.value.pattern.trim()) { formError.value = t('rules.errors.patternRequired'); return }
  if (!form.value.categoryId) { formError.value = t('rules.errors.categoryRequired'); return }
  saving.value = true
  try {
    const { splitPercent, ...rest } = form.value
    const payload = {
      ...rest,
      destination: form.value.destination || null,
      paidByPersonId: form.value.paidByPersonId || null,
      splitPersonId: form.value.destination === 'split' ? (form.value.splitPersonId || null) : null,
      splitRatio: form.value.destination === 'split' ? (Number(splitPercent) || 50) / 100 : null,
    }
    const res = props.initialRule?.id
      ? await api.put(`api/rules/${props.initialRule.id}`, payload)
      : await api.post('api/rules', payload)
    emit('saved', res.data)
  } catch (e) {
    formError.value = e?.response?.data?.detail || e.message || t('rules.errors.saveFailed')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.modal-backdrop { position:fixed; inset:0; background:rgba(0,0,0,.35); z-index:100; display:grid; place-items:center; }
.modal { background:#fff; width:480px; max-width:95vw; max-height:90vh; overflow-y:auto; border:1px solid #DDD9D0; display:flex; flex-direction:column; }
.modal-header { padding:16px 20px; border-bottom:1px solid #DDD9D0; display:flex; justify-content:space-between; align-items:center; font-size:14px; font-weight:600; }
.modal-body   { padding:20px; display:flex; flex-direction:column; gap:14px; }
.modal-footer { padding:16px 20px; border-top:1px solid #DDD9D0; display:flex; justify-content:flex-end; gap:8px; }
.form-row  { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
.form-group { display:flex; flex-direction:column; gap:6px; }
.label { font-size:12px; font-weight:500; color:#5C5752; }
.check { font-size:13px; display:flex; align-items:center; gap:6px; }
.input { padding:8px 11px; border:1px solid #DDD9D0; background:#F7F6F2; font-size:13px; font-family:inherit; outline:none; }
.input:focus { border-color:#1D3557; background:#fff; }
.form-error { font-size:12px; color:#E76F51; }
.field-hint { font-size:11px; color:#9A938C; line-height:1.4; }
.btn { display:inline-flex; align-items:center; gap:6px; padding:7px 14px; font-size:13px; cursor:pointer; border:1px solid #DDD9D0; background:#fff; color:#5C5752; }
.btn:disabled { opacity:.5; cursor:not-allowed; }
.btn-primary { background:#1D3557; color:#fff; border-color:#1D3557; }
.btn-icon { width:28px; height:28px; border:1px solid #DDD9D0; background:#fff; cursor:pointer; font-size:12px; display:grid; place-items:center; }
</style>
