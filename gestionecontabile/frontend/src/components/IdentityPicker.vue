<template>
  <div v-if="showPicker" class="modal-backdrop">
    <div class="modal">
      <div class="modal-header">{{ t('identityPicker.title') }}</div>
      <div class="modal-body">
        <p class="hint">{{ t('identityPicker.hint') }}</p>
        <button v-for="p in persons" :key="p.id" class="person-choice" @click="choose(p)">
          <span class="avatar" :style="{ background: p.color || '#1D3557' }">{{ initials(p.name) }}</span>
          {{ p.name }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'
import { getPersonId, setPersonId } from '../identity.js'

const { t } = useI18n()
const persons = ref([])
const showPicker = ref(false)

function initials(name) {
  return (name || '').split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

function choose(p) {
  setPersonId(p.id)
  showPicker.value = false
  window.location.reload()
}

onMounted(async () => {
  if (getPersonId()) return
  try {
    const [whoRes, personsRes] = await Promise.all([
      api.get('api/ha/whoami'),
      api.get('api/persons'),
    ])
    persons.value = personsRes.data
    if (whoRes.data.matchedPersonId) {
      setPersonId(whoRes.data.matchedPersonId)
      return
    }
    if (persons.value.length > 0) showPicker.value = true
  } catch {
    // Backend non raggiungibile o setup non ancora completato: si riprovera' al prossimo giro.
  }
})
</script>

<style scoped>
.modal-backdrop { position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:200; display:grid; place-items:center; }
.modal { background:#fff; width:360px; max-width:90vw; border:1px solid #DDD9D0; padding:24px; }
.modal-header { font-size:15px; font-weight:600; margin-bottom:10px; }
.hint { font-size:12.5px; color:#5C5752; line-height:1.5; margin-bottom:18px; }
.person-choice { display:flex; align-items:center; gap:12px; width:100%; padding:12px 14px; margin-bottom:8px; border:1px solid #DDD9D0; background:#F7F6F2; cursor:pointer; font-size:14px; font-family:inherit; text-align:left; }
.person-choice:hover { border-color:#1D3557; background:#fff; }
.avatar { width:32px; height:32px; border-radius:0; display:grid; place-items:center; font-size:12px; font-weight:700; color:#fff; flex-shrink:0; }
</style>
