<template>
  <div>
    <div class="topbar">
      <div class="topbar-title">{{ t('app.nav.guida') }}</div>
    </div>

    <div class="content">
      <div v-if="loading" class="empty">…</div>
      <div v-else-if="error" class="empty err">{{ error }}</div>
      <div v-else class="markdown-body" v-html="html"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { marked } from 'marked'

const { t } = useI18n()

const loading = ref(true)
const error   = ref('')
const html    = ref('')

onMounted(async () => {
  try {
    // guida.md e' un file statico in public/, servito con lo stesso base path
    // dell'app (relativo, vedi vite.config.js "base: './'") cosi' funziona
    // sia sotto HA Ingress sia sulla porta pubblica dedicata.
    const res = await fetch(`${import.meta.env.BASE_URL}guida.md`)
    if (!res.ok) throw new Error('not found')
    html.value = marked.parse(await res.text())
  } catch {
    error.value = 'Guida non disponibile'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.topbar { background:#fff; border-bottom:1px solid #DDD9D0; padding:0 28px; height:56px; display:flex; align-items:center; position:sticky; top:0; z-index:10; }
.topbar-title { font-size:15px; font-weight:600; }

.content { padding:28px; max-width:820px; }
.empty { text-align:center; padding:60px; color:#9A938C; font-size:13px; }
.err   { color:#E76F51; }

.markdown-body { font-size:14px; line-height:1.7; color:#3A3733; }
.markdown-body :deep(h1) { font-size:22px; font-weight:700; color:#1D3557; margin:0 0 16px; }
.markdown-body :deep(h2) { font-size:17px; font-weight:700; color:#1D3557; margin:32px 0 12px; padding-top:16px; border-top:1px solid #DDD9D0; }
.markdown-body :deep(h2:first-child) { margin-top:0; padding-top:0; border-top:none; }
.markdown-body :deep(p) { margin:0 0 12px; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { margin:0 0 12px; padding-left:22px; }
.markdown-body :deep(li) { margin-bottom:4px; }
.markdown-body :deep(strong) { color:#1D3557; }
.markdown-body :deep(code) { background:#F0EEE8; padding:1px 5px; font-size:12.5px; }
.markdown-body :deep(table) { border-collapse:collapse; width:100%; margin:0 0 16px; font-size:13px; }
.markdown-body :deep(th), .markdown-body :deep(td) { border:1px solid #DDD9D0; padding:8px 10px; text-align:left; }
.markdown-body :deep(th) { background:#F7F6F2; }
.markdown-body :deep(img) { max-width:100%; }
</style>
