<template>
  <div class="bar-chart">
    <div v-if="!rows.length" class="empty">{{ t('charts.noData') }}</div>
    <div v-for="(r, i) in rows" :key="r.label" class="bar-row">
      <div class="bar-label" :title="r.label">{{ r.label }}</div>
      <div class="bar-track">
        <div class="bar-fill" :style="{ width: pct(r.value) + '%', background: colorFor(i) }"></div>
      </div>
      <div class="bar-value num">{{ fmt(r.value) }}</div>
    </div>
  </div>
</template>

<script setup>
// Stesso pattern .bar-track/.bar-fill gia' usato in Reports.vue per le barre
// budget-per-categoria, generalizzato per righe {label, value} qualsiasi.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  rows: { type: Array, required: true }, // [{ label, value }]
})

const PALETTE = ['#1D3557', '#2A9D8F', '#E8A020', '#E76F51', '#7B2D8B', '#457B9D', '#A8DADC', '#9A938C']
function colorFor(i) { return PALETTE[i % PALETTE.length] }

const maxAbs = computed(() => Math.max(1, ...props.rows.map(r => Math.abs(r.value))))
function pct(v) { return Math.min(100, (Math.abs(v) / maxAbs.value) * 100) }

function fmt(v) {
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v || 0)
}
</script>

<style scoped>
.bar-chart { display: flex; flex-direction: column; gap: 10px; }
.bar-row { display: grid; grid-template-columns: 140px 1fr 90px; align-items: center; gap: 10px; font-size: 12px; }
.bar-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-track { height: 10px; background: #F0EEE9; border-radius: 2px; overflow: hidden; }
.bar-fill { height: 100%; transition: width .3s; border-radius: 2px; }
.bar-value { text-align: right; font-variant-numeric: tabular-nums; }
.empty { text-align: center; padding: 20px; color: #9A938C; font-size: 13px; }
</style>
