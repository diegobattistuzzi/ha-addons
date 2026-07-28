<template>
  <div class="pie-chart">
    <div v-if="!rows.length" class="empty">{{ t('charts.noData') }}</div>
    <template v-else>
      <div class="pie" :style="{ background: gradient }"></div>
      <div class="legend">
        <div v-for="(r, i) in rows" :key="r.label" class="legend-item">
          <span class="swatch" :style="{ background: colorFor(i) }"></span>
          <span class="legend-label" :title="r.label">{{ r.label }}</span>
          <span class="legend-value num">{{ fmt(r.value) }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
// Nessuna libreria di grafici nel progetto (TrendChart.vue e' gia' SVG scritto
// a mano): una torta con conic-gradient CSS resta coerente e non aggiunge una
// dipendenza solo per questo.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  rows: { type: Array, required: true }, // [{ label, value }]
})

const PALETTE = ['#1D3557', '#2A9D8F', '#E8A020', '#E76F51', '#7B2D8B', '#457B9D', '#A8DADC', '#9A938C']
function colorFor(i) { return PALETTE[i % PALETTE.length] }

const total = computed(() => props.rows.reduce((s, r) => s + Math.abs(r.value), 0) || 1)

const gradient = computed(() => {
  let acc = 0
  const stops = props.rows.map((r, i) => {
    const from = (acc / total.value) * 360
    acc += Math.abs(r.value)
    const to = (acc / total.value) * 360
    return `${colorFor(i)} ${from}deg ${to}deg`
  })
  return `conic-gradient(${stops.join(', ')})`
})

function fmt(v) {
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v || 0)
}
</script>

<style scoped>
.pie-chart { display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }
.pie { width: 140px; height: 140px; border-radius: 50%; flex-shrink: 0; }
.legend { display: flex; flex-direction: column; gap: 6px; font-size: 12px; min-width: 0; flex: 1; }
.legend-item { display: flex; align-items: center; gap: 8px; }
.swatch { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
.legend-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.legend-value { margin-left: auto; font-variant-numeric: tabular-nums; padding-left: 10px; }
.empty { text-align: center; padding: 20px; color: #9A938C; font-size: 13px; }
</style>
