<template>
  <div class="cat-picker">
    <input
      ref="inputEl"
      class="input cat-picker-input"
      :class="inputClass"
      v-model="query"
      :placeholder="placeholder"
      autocomplete="off"
      @focus="onFocus"
      @blur="onBlur"
      @keydown="onKeydown"
    />
    <div v-if="open" class="cat-picker-list">
      <div class="cat-picker-opt" :class="{ hl: highlighted === -1 }" @mousedown.prevent="choose(null)">
        {{ clearLabel }}
      </div>
      <div v-for="(c, i) in filtered" :key="c.id" class="cat-picker-opt" :class="{ hl: i === highlighted, child: c.depth }"
        @mousedown.prevent="choose(c)">
        <span v-if="c.depth">↳ </span>{{ c.icon }} {{ c.name }}
      </div>
      <div v-if="!filtered.length" class="cat-picker-empty">{{ t('categoryPicker.noResults') }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { sortCategoriesAsTree } from '../utils/categoryTree.js'

const { t } = useI18n()

const props = defineProps({
  modelValue: { type: [Number, String, null], default: '' },
  categories: { type: Array, required: true },
  clearLabel: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  inputClass: { type: String, default: '' },
  autofocus: { type: Boolean, default: false },
})

const clearLabel = computed(() => props.clearLabel || t('categoryPicker.clearLabel'))
const placeholder = computed(() => props.placeholder || t('categoryPicker.placeholder'))
const emit = defineEmits(['update:modelValue', 'blur-close'])

const query = ref('')
const open = ref(false)
const highlighted = ref(-1)
const inputEl = ref(null)

// Albero a 2 livelli (padre poi le sue sotto-categorie, entrambi alfabetici)
// invece del semplice ordine alfabetico piatto: la gerarchia scelta in
// Impostazioni > Categorie deve restare visibile anche qui, non solo li'.
const sorted = computed(() => sortCategoriesAsTree(props.categories))

const selected = computed(() => props.categories.find(c => c.id === props.modelValue) || null)
const displayLabel = c => (c ? `${c.icon} ${c.name}` : '')

watch(
  () => props.modelValue,
  () => { if (!open.value) query.value = displayLabel(selected.value) },
  { immediate: true }
)

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return sorted.value
  return sorted.value.filter(c => c.name.toLowerCase().includes(q))
})

function onFocus() {
  open.value = true
  query.value = ''
  highlighted.value = -1
}

function onBlur() {
  open.value = false
  query.value = displayLabel(selected.value)
  emit('blur-close')
}

onMounted(() => {
  if (props.autofocus) inputEl.value?.focus()
})

function choose(c) {
  emit('update:modelValue', c ? c.id : '')
  query.value = displayLabel(c)
  open.value = false
}

function onKeydown(e) {
  if (!open.value) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    highlighted.value = Math.min(highlighted.value + 1, filtered.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    highlighted.value = Math.max(highlighted.value - 1, -1)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (highlighted.value === -1) choose(null)
    else choose(filtered.value[highlighted.value])
  } else if (e.key === 'Escape') {
    open.value = false
    query.value = displayLabel(selected.value)
    inputEl.value?.blur()
  }
}
</script>

<style scoped>
.cat-picker { position: relative; }
.cat-picker-input { width: 100%; }
.cat-picker-list {
  position: absolute; top: calc(100% + 2px); left: 0; right: 0; z-index: 50;
  background: #fff; border: 1px solid #DDD9D0; max-height: 240px; overflow-y: auto;
  box-shadow: 0 4px 12px rgba(0,0,0,.08);
}
.cat-picker-opt { padding: 7px 11px; font-size: 13px; cursor: pointer; }
.cat-picker-opt.child { padding-left: 22px; color: #5C5752; background: #FBFAF8; }
.cat-picker-opt:hover, .cat-picker-opt.hl { background: #EBF0F6; }
.cat-picker-empty { padding: 7px 11px; font-size: 12px; color: #9A938C; }
</style>
