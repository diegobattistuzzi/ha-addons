<template>
  <div class="trend-chart">
    <div v-if="!rows.length" class="empty">{{ t('charts.trend.noDataPeriod') }}</div>
    <template v-else>
      <svg :viewBox="`0 0 ${width} ${height}`" class="trend-svg" preserveAspectRatio="none">
        <!-- griglia leggera: solo la linea di zero, gli assi restano recessivi -->
        <line :x1="padLeft" :x2="width" :y1="zeroY" :y2="zeroY" class="baseline" />

        <g v-for="(r, i) in rows" :key="r.month">
          <!-- area di hover: tutta la banda del mese, piu' larga delle barre vere -->
          <rect
            :x="bandX(i)" :y="8" :width="bandWidth" :height="height - 28"
            class="hit-area"
            @mouseenter="hovered = i" @mouseleave="hovered = null"
          />

          <!-- entrate: verso l'alto dalla linea di zero -->
          <rect v-if="r.income > 0"
            :x="barX(i)" :y="zeroY - scale(r.income)" :width="barWidth" :height="scale(r.income)"
            class="seg seg-income" :class="{ dim: hovered !== null && hovered !== i }" rx="2"
          />

          <!-- spese famiglia: verso il basso dalla linea di zero -->
          <rect v-if="r.family > 0"
            :x="barX(i)" :y="zeroY + gap" :width="barWidth" :height="scale(r.family)"
            class="seg seg-family" :class="{ dim: hovered !== null && hovered !== i }" rx="2"
          />
          <!-- spese personali: sotto il segmento famiglia, separate da un piccolo gap -->
          <rect v-if="r.personal > 0"
            :x="barX(i)" :y="zeroY + gap + scale(r.family) + (r.family > 0 ? gap : 0)" :width="barWidth" :height="scale(r.personal)"
            class="seg seg-personal" :class="{ dim: hovered !== null && hovered !== i }" rx="2"
          />

          <text :x="bandX(i) + bandWidth / 2" :y="height - 6" text-anchor="middle" class="axis-label">{{ monthLabel(r.month) }}</text>
        </g>
      </svg>

      <div v-if="hovered !== null" class="tooltip" :style="tooltipStyle">
        <div class="tooltip-title">{{ monthLabel(rows[hovered].month, true) }}</div>
        <div class="tooltip-row"><span class="swatch swatch-income"></span>{{ t('charts.trend.income') }}<span class="tooltip-val">{{ fmt(rows[hovered].income) }}</span></div>
        <div class="tooltip-row"><span class="swatch swatch-family"></span>{{ t('charts.trend.familyExpenses') }}<span class="tooltip-val">{{ fmt(rows[hovered].family) }}</span></div>
        <div class="tooltip-row"><span class="swatch swatch-personal"></span>{{ t('charts.trend.personalExpenses') }}<span class="tooltip-val">{{ fmt(rows[hovered].personal) }}</span></div>
      </div>

      <div class="legend">
        <span class="legend-item"><span class="swatch swatch-income"></span>{{ t('charts.trend.income') }}</span>
        <span class="legend-item"><span class="swatch swatch-family"></span>{{ t('charts.trend.familyExpenses') }}</span>
        <span class="legend-item"><span class="swatch swatch-personal"></span>{{ t('charts.trend.personalExpenses') }}</span>
      </div>

      <table class="trend-table">
        <thead>
          <tr><th>{{ t('charts.trend.month') }}</th><th>{{ t('charts.trend.income') }}</th><th>{{ t('charts.trend.familyExpenses') }}</th><th>{{ t('charts.trend.personalExpenses') }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.month">
            <td>{{ monthLabel(r.month, true) }}</td>
            <td class="num">{{ fmt(r.income) }}</td>
            <td class="num">{{ fmt(r.family) }}</td>
            <td class="num">{{ fmt(r.personal) }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  rows: { type: Array, required: true }, // [{ month:'2026-06', family, personal, income }]
})

const hovered = ref(null)

const width = 560
const height = 220
const padLeft = 4
const gap = 2 // spacer tra i segmenti impilati e tra la barra e la linea di zero

const zeroY = height / 2
const halfHeight = height / 2 - 20 // margine per le etichette dei mesi in basso e respiro in alto

const maxUp = computed(() => Math.max(1, ...props.rows.map(r => r.income)))
const maxDown = computed(() => Math.max(1, ...props.rows.map(r => r.family + r.personal)))
const maxValue = computed(() => Math.max(maxUp.value, maxDown.value))
const pxPerEuro = computed(() => halfHeight / maxValue.value)
function scale(v) { return v * pxPerEuro.value }

const bandWidth = computed(() => (width - padLeft) / Math.max(1, props.rows.length))
const barWidth = computed(() => bandWidth.value * 0.5)
function bandX(i) { return padLeft + i * bandWidth.value }
function barX(i) { return bandX(i) + (bandWidth.value - barWidth.value) / 2 }

function monthLabel(m, long = false) {
  const [y, mo] = m.split('-')
  const d = new Date(Number(y), Number(mo) - 1, 1)
  return d.toLocaleDateString('it-IT', long ? { month: 'long', year: 'numeric' } : { month: 'short' })
}

const tooltipStyle = computed(() => {
  if (hovered.value === null) return {}
  const left = (bandX(hovered.value) + bandWidth.value / 2) / width * 100
  return { left: `${left}%` }
})

function fmt(v) {
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v || 0)
}
</script>

<style scoped>
/* Colori riusati dal resto dell'app (chip destinazione, .pos/.neg) invece di
   introdurne di nuovi: teal = entrate (come .pos ovunque), ambra = spese
   personali (come chip-personal), viola = spese famiglia (unico accento
   rimasto libero con contrasto/CVD sufficiente rispetto ai due sopra -
   validato con lo script della skill dataviz). Nessuna modalita' scura: il
   resto dell'app non la supporta, quindi non la introduco solo qui. */
.trend-chart { position: relative; }
.trend-svg { width: 100%; height: 220px; display: block; }
.baseline { stroke: #C3C2B7; stroke-width: 1; }
.hit-area { fill: transparent; }
.seg { transition: opacity .15s; }
.seg.dim { opacity: .35; }
.seg-income   { fill: #2A9D8F; }
.seg-family   { fill: #7B2D8B; }
.seg-personal { fill: #E8A020; }
.axis-label { font-size: 10px; fill: #9A938C; text-transform: capitalize; }

.legend { display: flex; gap: 16px; justify-content: center; margin-top: 4px; font-size: 11.5px; color: #5C5752; }
.legend-item { display: inline-flex; align-items: center; gap: 6px; }
.swatch { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }
.swatch-income   { background: #2A9D8F; }
.swatch-family   { background: #7B2D8B; }
.swatch-personal { background: #E8A020; }

.tooltip {
  position: absolute; top: 8px; transform: translateX(-50%);
  background: #1D3557; color: #fff; padding: 8px 10px; font-size: 11.5px;
  border-radius: 3px; pointer-events: none; white-space: nowrap; z-index: 5;
  box-shadow: 0 4px 10px rgba(0,0,0,.15);
}
.tooltip-title { font-weight: 600; margin-bottom: 4px; text-transform: capitalize; }
.tooltip-row { display: flex; align-items: center; gap: 6px; }
.tooltip-val { margin-left: auto; font-variant-numeric: tabular-nums; padding-left: 10px; }

/* Tabella dati equivalente al grafico, per accessibilita' e per chi preferisce
   i numeri esatti invece delle barre. */
.trend-table { width: 100%; margin-top: 14px; font-size: 11.5px; border-collapse: collapse; }
.trend-table th { text-align: right; color: #9A938C; font-weight: 500; padding: 4px 6px; border-bottom: 1px solid #DDD9D0; }
.trend-table th:first-child, .trend-table td:first-child { text-align: left; text-transform: capitalize; }
.trend-table td { text-align: right; padding: 4px 6px; border-bottom: 1px solid #F0EEE9; font-variant-numeric: tabular-nums; }
.empty { text-align: center; padding: 40px; color: #9A938C; font-size: 13px; }
</style>
