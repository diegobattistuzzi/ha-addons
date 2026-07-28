<template>
  <div>
    <!-- Topbar -->
    <div class="topbar">
      <div>
        <div class="topbar-title">{{ t('transactions.topbar.title') }}</div>
        <div class="topbar-meta">{{ t('transactions.topbar.count', { count: total }) }}</div>
      </div>
      <div class="topbar-actions">
        <button class="btn btn-sm" @click="openManual">{{ t('transactions.actions.manualAdd') }}</button>
        <button class="btn btn-primary btn-sm" @click="showImport = true">{{ t('transactions.actions.importBank') }}</button>
      </div>
    </div>

    <div class="content">

      <!-- Aggiungi spesa con AI -->
      <div class="ai-quick-add">
        <input class="input ai-quick-input" v-model="aiQuickText" :placeholder="t('transactions.aiQuickAdd.placeholder')"
          :disabled="aiQuickLoading" @keyup.enter="aiQuickAdd" />
        <button class="btn btn-sm" :disabled="aiQuickLoading || !aiQuickText.trim()" @click="aiQuickAdd">
          {{ aiQuickLoading ? '...' : t('transactions.aiQuickAdd.analyze') }}
        </button>
        <span v-if="aiQuickError" class="ai-quick-error">{{ aiQuickError }}</span>
      </div>

      <!-- Banner AI pendenti -->
      <div v-if="pendingAI.length" class="ai-banner">
        <span>✦ <strong>{{ pendingAI.length }}</strong> {{ t('transactions.aiBanner.text') }}</span>
        <button class="btn btn-sm" @click="filterConfirmed = 'pending'; load()">{{ t('transactions.aiBanner.show') }}</button>
        <button class="btn btn-sm btn-teal" @click="confirmAll">{{ t('transactions.aiBanner.approveAll') }}</button>
      </div>

      <!-- Banner rimborsi lavoro in attesa -->
      <div v-if="totalPendingReimbursement > 0" class="reimb-banner">
        <span>💶 <strong>{{ fmt(totalPendingReimbursement) }}</strong> {{ t('transactions.reimbBanner.text') }}</span>
        <button class="btn btn-sm" @click="filterReimb = 'pending'; load()">{{ t('transactions.reimbBanner.show') }}</button>
      </div>

      <!-- Filtri -->
      <div class="filters">
        <input class="input filter-input" v-model="filterText" :placeholder="t('transactions.filters.search')" />
        <select class="input filter-sel" v-model="filterAccount">
          <option value="">{{ t('transactions.filters.allAccounts') }}</option>
          <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
        </select>
        <select class="input filter-sel" v-model="filterCategory">
          <option value="">{{ t('transactions.filters.allCategories') }}</option>
          <option v-for="c in activeCategoriesTree" :key="c.id" :value="c.id">{{ c.depth ? '↳ ' : '' }}{{ c.icon }} {{ c.name }}</option>
        </select>
        <select class="input filter-sel" v-model="filterDest">
          <option value="">{{ t('transactions.filters.all') }}</option>
          <option value="family">{{ t('transactions.destination.family') }}</option>
          <option value="personal">{{ t('transactions.filters.personalAll') }}</option>
          <option v-for="p in persons" :key="p.id" :value="`personal:${p.id}`">{{ t('transactions.filters.personalOf', { name: p.name }) }}</option>
          <option value="split">{{ t('transactions.destination.split') }}</option>
        </select>
        <select class="input filter-sel" v-model="filterReimb">
          <option value="">{{ t('transactions.filters.reimbAll') }}</option>
          <option value="pending">{{ t('transactions.filters.reimbPending') }}</option>
          <option value="reimbursed">{{ t('transactions.filters.reimbReimbursed') }}</option>
        </select>
        <select class="input filter-sel" v-model="filterConfirmed">
          <option value="">{{ t('transactions.filters.statusAll') }}</option>
          <option value="pending">{{ t('transactions.filters.statusPending') }}</option>
          <option value="confirmed">{{ t('transactions.filters.statusConfirmed') }}</option>
        </select>
        <input class="input filter-input" type="month" v-model="filterMonth" />
        <button class="btn btn-sm" @click="load">{{ t('transactions.filters.filterBtn') }}</button>
      </div>

      <!-- Barra azioni di gruppo -->
      <div v-if="selectedIds.size" class="bulk-bar">
        <span class="bulk-count">{{ t('transactions.bulkBar.selectedCount', { count: selectedIds.size }) }}</span>
        <CategoryPicker v-model="bulkForm.categoryId" :categories="activeCategories"
          :clear-label="t('transactions.bulkBar.categoryNoChange')" :placeholder="t('transactions.bulkBar.categoryNoChange')" input-class="input-sm bulk-cat-input" />
        <select class="input input-sm" v-model="bulkForm.accountId">
          <option value="">{{ t('transactions.bulkBar.accountNoChange') }}</option>
          <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
        </select>
        <select class="input input-sm" v-model="bulkForm.destination">
          <option value="">{{ t('transactions.bulkBar.destNoChange') }}</option>
          <option value="family">{{ t('transactions.destination.family') }}</option>
          <option value="personal">{{ t('transactions.destination.personal') }}</option>
          <option value="split">{{ t('transactions.destination.split') }}</option>
        </select>
        <select class="input input-sm" v-model="bulkForm.paidByPersonId">
          <option value="">{{ t('transactions.bulkBar.paidByNoChange') }}</option>
          <option value="__clear__">{{ t('transactions.bulkBar.clearOption') }}</option>
          <option v-for="p in persons" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
        <select class="input input-sm" v-model="bulkForm.isReimbursable">
          <option value="">{{ t('transactions.bulkBar.reimbNoChange') }}</option>
          <option value="true">{{ t('transactions.bulkBar.markReimbursable') }}</option>
        </select>
        <button class="btn btn-sm btn-teal" @click="applyBulk" :disabled="bulkApplying">
          {{ bulkApplying ? '...' : t('transactions.bulkBar.apply') }}
        </button>
        <button class="btn btn-sm" @click="bulkConfirm" :disabled="bulkApplying">{{ t('transactions.bulkBar.confirm') }}</button>
        <button class="btn btn-sm" @click="bulkRejectAi" :disabled="bulkApplying">{{ t('transactions.bulkBar.rejectAi') }}</button>
        <button class="btn btn-sm" @click="bulkCategorizeAi" :disabled="bulkApplying">{{ t('transactions.bulkBar.categorizeAi') }}</button>
        <button class="btn btn-sm btn-danger" @click="bulkDelete" :disabled="bulkApplying">{{ t('transactions.bulkBar.delete') }}</button>
        <button class="btn btn-sm" @click="clearSelection">{{ t('transactions.bulkBar.deselect') }}</button>
      </div>

      <!-- Lista -->
      <div class="tx-list">
        <div class="tx-header">
          <div><input type="checkbox" :checked="allSelected" @change="toggleSelectAll" /></div>
          <div></div>
          <div class="sortable" @click="toggleSort('date')">{{ t('common.date') }}<span v-if="sortKey==='date'" class="sort-arrow">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></div>
          <div>{{ t('transactions.list.header.transaction') }}</div>
          <div>{{ t('common.category') }}</div>
          <div>{{ t('transactions.list.header.dest') }}</div>
          <div>{{ t('transactions.list.header.from') }}</div>
          <div class="sortable" @click="toggleSort('amount')">{{ t('common.amount') }}<span v-if="sortKey==='amount'" class="sort-arrow">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></div>
          <div>{{ t('transactions.list.header.account') }}</div>
          <div></div>
        </div>
        <div v-if="loading" class="empty">{{ t('common.loading') }}</div>
        <div v-else-if="loadError" class="empty error-msg">
          ✕ {{ loadError }}<br>
          <small>{{ t('transactions.list.checkBackend') }}</small>
        </div>
        <div v-else-if="!filtered.length" class="empty">
          {{ t('transactions.list.empty') }}
          <span v-if="!transactions.length"> {{ t('transactions.list.emptyHint') }}</span>
        </div>
        <div v-for="tx in filtered" :key="tx.id" class="tx-row" :class="{ pending: !tx.is_confirmed }">
          <div><input type="checkbox" :checked="selectedIds.has(tx.id)" @change="toggleSelect(tx.id)" /></div>
          <div class="tx-icon">{{ categoryIcon(tx.category_id) }}</div>
          <div class="tx-date">{{ tx.date }}</div>
          <div>
            <div class="tx-name">{{ tx.merchant_name || tx.description_raw || '—' }}</div>
            <div v-if="tx.notes" class="tx-desc">{{ tx.notes }}</div>
            <div v-if="tx.document_id || tx.attachment_count || tx.email_receipt_id" class="tx-links">
              <a v-if="tx.document_id" :href="downloadUrl(tx.document_id)" target="_blank" class="tx-link" :title="t('transactions.row.openSourceStatement')">📄</a>
              <button v-if="tx.attachment_count" class="tx-link" @click="editTx(tx)" :title="t('transactions.row.attachmentsTitle', { count: tx.attachment_count })">📎 {{ tx.attachment_count }}</button>
              <RouterLink v-if="tx.email_receipt_id" :to="`/email?highlight=${tx.email_receipt_id}`" class="tx-link" :title="t('transactions.row.goToMatchedEmail')">✉</RouterLink>
            </div>
          </div>
          <div class="tx-cat-cell">
            <CategoryPicker v-if="inlineCategoryId === tx.id"
              :model-value="tx.category_id ?? tx.ai_category_id ?? ''"
              :categories="categoryOptionsFor(tx)"
              input-class="input-sm"
              autofocus
              @update:modelValue="val => onInlineCategoryChange(tx, val)"
              @blur-close="inlineCategoryId = null"
            />
            <template v-else>
              <span class="chip chip-editable" :class="tx.is_confirmed ? '' : 'chip-ai'"
                @click="inlineCategoryId = tx.id" :title="t('transactions.row.clickToChangeCategory')">
                {{ categoryName(tx.category_id ?? tx.ai_category_id) || '—' }}
                <span v-if="!tx.is_confirmed && tx.ai_category_id"> ✦</span>
              </span>
              <button v-if="!tx.is_confirmed && tx.ai_category_id" class="btn-icon-mini"
                @click="confirmAiCategory(tx)" :title="t('transactions.row.confirmAiCategory')">✓</button>
            </template>
          </div>
          <div class="tx-dest-cell">
            <select v-if="inlineDestId === tx.id" class="input input-sm" autofocus
              :value="tx.destination"
              @change="e => onInlineDestChange(tx, e.target.value)"
              @blur="inlineDestId = null">
              <option value="family">{{ t('transactions.destination.family') }}</option>
              <option value="personal">{{ t('transactions.destination.personal') }}</option>
              <option value="split">{{ t('transactions.destination.split') }}</option>
            </select>
            <span v-else class="chip chip-editable" :class="`chip-${tx.destination}`"
              @click="inlineDestId = tx.id" :title="t('transactions.row.clickToChangeDest')">{{ destLabel(tx.destination) }}</span>
            <span v-if="tx.is_reimbursable" class="chip" :class="tx.reimbursed_at ? 'chip-reimb-done' : 'chip-reimb'"
              :title="tx.reimbursed_at ? t('transactions.row.reimbursedOn', { date: tx.reimbursed_at }) : t('transactions.row.toReimburse', { amount: fmt(reimbursementAmountOf(tx)) })">
              {{ tx.reimbursed_at ? t('transactions.row.reimbDoneBadge') : `↩ ${fmt(reimbursementAmountOf(tx))}` }}
            </span>
          </div>
          <div class="tx-person">{{ personName(tx.paid_by_person_id) }}</div>
          <div class="tx-amount num" :class="tx.amount < 0 ? 'neg' : 'pos'">{{ fmt(tx.amount) }}</div>
          <div class="tx-acc">{{ accountName(tx.account_id) }}</div>
          <div class="tx-actions">
            <button v-if="tx.is_reimbursable" class="btn-icon" @click="toggleReimbursed(tx)"
              :title="tx.reimbursed_at ? t('transactions.row.reopenTitle') : t('transactions.row.markReimbursedTitle')">
              {{ tx.reimbursed_at ? '↺' : '✓' }}
            </button>
            <button class="btn-icon" @click="editTx(tx)" :title="t('common.edit')">✎</button>
            <button class="btn-icon danger" @click="deleteTx(tx)" :title="t('common.delete')">✕</button>
          </div>
        </div>
      </div>

    </div>

    <!-- Modal inserimento manuale -->
    <div v-if="showManual" class="modal-backdrop" @click.self="showManual=false">
      <div class="modal">
        <div class="modal-header">
          <span>{{ editMode ? t('transactions.manualModal.editTitle') : t('transactions.manualModal.newTitle') }}</span>
          <button class="btn-icon" @click="showManual=false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <div class="form-group">
              <label class="label">{{ t('transactions.manualModal.dateLabel') }}</label>
              <input class="input" type="date" v-model="form.date" required />
            </div>
            <div class="form-group">
              <label class="label">{{ t('transactions.manualModal.amountLabel') }}</label>
              <input class="input" type="number" step="0.01" v-model="form.amount" placeholder="-42.50" required />
            </div>
          </div>
          <div class="form-group">
            <label class="label">{{ t('transactions.manualModal.descriptionLabel') }}</label>
            <input class="input" v-model="form.description" :placeholder="t('transactions.manualModal.descriptionPlaceholder')" required />
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="label">{{ t('transactions.manualModal.accountLabel') }}</label>
              <select class="input" v-model="form.accountId" required @change="onAccountChange">
                <option value="">{{ t('transactions.manualModal.selectPlaceholder') }}</option>
                <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
              </select>
            </div>
            <div class="form-group">
              <label class="label">{{ t('common.category') }}</label>
              <CategoryPicker v-model="form.categoryId" :categories="formCategoryOptions" />
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="label">{{ t('transactions.manualModal.destinationLabel') }}</label>
              <select class="input" v-model="form.destination">
                <option value="family">{{ t('transactions.manualModal.destFamily') }}</option>
                <option value="personal">{{ t('transactions.destination.personal') }}</option>
                <option value="split">{{ t('transactions.manualModal.destSplit') }}</option>
              </select>
            </div>
            <div class="form-group">
              <label class="label">{{ t('transactions.manualModal.paidByLabel') }}</label>
              <select class="input" v-model="form.paidByPersonId">
                <option value="">{{ t('transactions.manualModal.notSpecified') }}</option>
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
            <div class="form-group" style="justify-content:flex-end; padding-top:24px;">
              <label class="check"><input type="checkbox" v-model="form.isCash" /> {{ t('transactions.manualModal.cashLabel') }}</label>
            </div>
            <div class="form-group" style="justify-content:flex-end; padding-top:24px;">
              <label class="check"><input type="checkbox" v-model="form.isReimbursable" /> {{ t('transactions.manualModal.reimbursableLabel') }}</label>
            </div>
          </div>
          <div v-if="form.isReimbursable" class="form-group">
            <label class="label">{{ t('transactions.manualModal.reimbAmountLabel') }}</label>
            <input class="input" type="number" step="0.01" v-model="form.reimbursementAmount"
              :placeholder="form.amount !== '' ? String(Math.abs(Number(form.amount))) : '0.00'" />
          </div>
          <div class="form-group">
            <label class="label">{{ t('transactions.manualModal.notesLabel') }}</label>
            <input class="input" v-model="form.notes" :placeholder="t('transactions.manualModal.notesPlaceholder')" />
          </div>

          <div v-if="editMode" class="form-group">
            <label class="label">{{ t('transactions.manualModal.attachmentsLabel') }}</label>
            <div v-if="txAttachments.length" class="attachment-list">
              <div v-for="d in txAttachments" :key="d.id" class="attachment-row">
                <a :href="downloadUrl(d.id)" target="_blank" class="attachment-name">📎 {{ d.filename }}</a>
                <button class="btn-icon danger" @click="deleteAttachment(d)" :title="t('transactions.manualModal.removeAttachmentTitle')">✕</button>
              </div>
            </div>
            <label class="btn btn-sm attachment-upload">
              {{ attachmentUploading ? t('transactions.manualModal.uploading') : t('transactions.manualModal.addAttachment') }}
              <input type="file" style="display:none" :disabled="attachmentUploading" @change="onAttachmentFileChange" />
            </label>
          </div>
        </div>
        <div class="modal-footer">
          <span v-if="formError" class="form-error">{{ formError }}</span>
          <button class="btn" @click="showManual=false">{{ t('common.cancel') }}</button>
          <button class="btn btn-primary" @click="saveManual" :disabled="saving">
            {{ saving ? '...' : (editMode ? t('transactions.manualModal.saveChanges') : t('common.add')) }}
          </button>
        </div>
      </div>
    </div>

    <!-- Modal importazione -->
    <div v-if="showImport" class="modal-backdrop" @click.self="closeImport">
      <div class="modal modal-import">
        <div class="modal-header">
          <span>{{ t('transactions.importModal.title') }}</span>
          <button class="btn-icon" @click="closeImport">✕</button>
        </div>

        <!-- Step 1: selezione file -->
        <div v-if="importStep === 'select'" class="modal-body">
          <div class="import-formats">
            <div class="format-card" @click="pickFile">
              <div class="format-icon">📄</div>
              <div class="format-name">CSV</div>
              <div class="format-desc">{{ t('transactions.importModal.csvDesc') }}</div>
            </div>
            <div class="format-card" @click="pickFile">
              <div class="format-icon">📊</div>
              <div class="format-name">Excel (.xlsx)</div>
              <div class="format-desc">{{ t('transactions.importModal.excelDesc') }}</div>
            </div>
            <div class="format-card ai-badge" @click="pickFile">
              <div class="format-icon">📑</div>
              <div class="format-name">PDF <span class="ai-tag">✦ AI</span></div>
              <div class="format-desc">{{ t('transactions.importModal.pdfDesc') }}</div>
            </div>
          </div>

          <div class="form-group" style="margin-top:16px;">
            <label class="label">{{ t('transactions.importModal.linkAccountLabel') }}</label>
            <select class="input" v-model="importAccountId">
              <option value="">{{ t('transactions.importModal.autoDetect') }}</option>
              <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
            </select>
            <div v-if="importAccountOwnership === 'personal'" class="import-hint">
              🔒 {{ t('transactions.importModal.personalAccountHint', { name: personName(importAccountOwnerId) || t('transactions.importModal.thisOwner') }) }}
            </div>
          </div>

          <label class="upload-zone" :class="{ dragover: isDragover }"
            @dragover.prevent="isDragover=true"
            @dragleave="isDragover=false"
            @drop.prevent="onDrop">
            <input type="file" accept=".csv,.pdf,.xlsx,.xls" style="display:none" ref="fileInput" @change="onFileChange" />
            <div class="upload-icon">↑</div>
            <div class="upload-text">{{ t('transactions.importModal.dragText') }} <span class="link">{{ t('transactions.importModal.dragLink') }}</span></div>
            <div class="upload-hint">{{ t('transactions.importModal.dragHint') }}</div>
          </label>
        </div>

        <!-- Step 2: caricamento -->
        <div v-if="importStep === 'loading'" class="modal-body modal-center">
          <div class="spinner"></div>
          <div class="loading-text">
            <strong>{{ t('transactions.importModal.analyzing') }}</strong>
            <div>{{ importFile?.name }}</div>
            <div v-if="importFile?.name?.endsWith('.pdf')" class="hint-ai">
              ✦ {{ importStreamStage || t('transactions.importModal.aiReadingPdf') }}
              <span v-if="importStreamCount">— {{ t('transactions.importModal.foundCount', { count: importStreamCount }) }}</span>
            </div>
            <div v-if="importStreamAccount" class="hint-ai">
              🏦 {{ t('transactions.importModal.detectedBank', { bank: importStreamAccount.bankName || t('transactions.importModal.unknownBank') }) }}
              <span v-if="importStreamAccount.iban">— {{ t('transactions.importModal.ibanLabel', { iban: importStreamAccount.iban }) }}</span>
              <span v-else-if="importStreamAccount.cardNumber">— {{ t('transactions.importModal.cardLabel', { card: importStreamAccount.cardNumber }) }}</span>
            </div>
          </div>
        </div>

        <!-- Step 3: risultato -->
        <div v-if="importStep === 'done'" class="modal-body">
          <div class="result-badge" :class="importResult.error ? 'result-err' : 'result-ok'">
            <div class="result-icon">{{ importResult.error ? '✕' : '✓' }}</div>
            <div>
              <div class="result-title">{{ importResult.error ? t('transactions.importModal.importError') : t('transactions.importModal.importedCount', { count: importResult.count }) }}</div>
              <div class="result-sub">
                {{ importResult.error || `${t('transactions.importModal.fromFile', { filename: importResult.filename })}${importResult.bank && importResult.bank !== 'sconosciuta' ? ' · ' + importResult.bank : ''}${importResult.usedAi ? ' · ' + t('transactions.importModal.aiAnalyzed') : ''}` }}
              </div>
              <div v-if="!importResult.error && importResult.aiCategorized" class="result-sub">
                ✦ {{ t('transactions.importModal.aiCategorizedCount', { count: importResult.aiCategorized }) }}
              </div>
              <div v-if="!importResult.error && importResult.duplicates" class="result-sub">
                ↩️ {{ t('transactions.importModal.duplicatesIgnored', { count: importResult.duplicates }) }}
              </div>
            </div>
          </div>

          <div v-if="importResult.signWarning" class="warning-box">⚠️ {{ importResult.signWarning }}</div>
          <div v-if="importResult.reconciliationWarning" class="warning-box">⚠️ {{ importResult.reconciliationWarning }}</div>

          <div v-if="!importResult.error && importResult.preview?.length" class="preview-list">
            <div class="preview-header">{{ t('transactions.importModal.previewHeader') }}</div>
            <div v-for="(row, i) in importResult.preview" :key="i" class="preview-row">
              <span class="preview-date">{{ row.date }}</span>
              <span class="preview-desc">{{ row.description || '—' }}</span>
              <span class="preview-amount" :class="row.amount < 0 ? 'neg' : 'pos'">
                {{ fmtPreview(row.amount) }}
              </span>
            </div>
          </div>

          <div v-if="!importResult.error" class="info-box" style="margin-top:12px;">
            {{ t('transactions.importModal.importedAsUnconfirmed') }}
          </div>

          <div v-if="importResult.suggestedTransfers?.length" class="transfer-suggestions">
            <div class="preview-header">🔁 {{ t('transactions.importModal.transferSuggestionsHeader') }}</div>
            <div v-for="s in importResult.suggestedTransfers" :key="s.transactionId" class="suggestion-row">
              <div class="suggestion-info">
                <div>{{ s.description || '—' }} <span class="num">{{ fmtPreview(s.amount) }}</span></div>
                <div class="suggestion-sub">{{ t('transactions.importModal.suggestionMatch', { date: s.date, cardAccountName: s.cardAccountName, matchedAmount: fmtPreview(-s.matchedCardTotal) }) }}</div>
              </div>
              <button class="btn btn-sm" :disabled="markedTransferIds.has(s.transactionId)" @click="markAsTransfer(s)">
                {{ markedTransferIds.has(s.transactionId) ? t('transactions.importModal.markedTransfer') : t('transactions.importModal.markAsTransferBtn') }}
              </button>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <button v-if="importStep === 'done'" class="btn btn-primary" @click="closeImport">{{ t('common.close') }}</button>
          <button v-else class="btn" @click="closeImport">{{ t('common.cancel') }}</button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'
import { getPersonId } from '../identity.js'
import CategoryPicker from '../components/CategoryPicker.vue'
import { sortCategoriesAsTree } from '../utils/categoryTree.js'

const { t } = useI18n()

const transactions   = ref([])
const pendingAI      = ref([])
const categories     = ref([])
const accounts       = ref([])
const persons        = ref([])
const loading        = ref(true)
const loadError      = ref('')
const total          = ref(0)

// selezione multipla / azioni di gruppo
const selectedIds  = ref(new Set())
const bulkApplying = ref(false)
const emptyBulkForm = () => ({ categoryId: '', accountId: '', destination: '', paidByPersonId: '', isReimbursable: '' })
const bulkForm = ref(emptyBulkForm())

// import modal
const showImport     = ref(false)
const importStep     = ref('select')   // select | loading | done
const importAccountId = ref('')
const importFile     = ref(null)
const importResult   = ref({})
const isDragover     = ref(false)
const fileInput      = ref(null)

// ordinamento colonne (client-side, sui dati gia' caricati/filtrati)
const sortKey = ref('date')
const sortDir = ref('desc')
function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'asc'
  }
}

const filterText    = ref('')
const filterAccount = ref('')
const filterCategory = ref('')
const filterDest    = ref('')
const filterReimb   = ref('')
const filterConfirmed = ref('')
const filterMonth   = ref('')

// modifica inline della categoria direttamente in lista (senza aprire il modal)
const inlineCategoryId = ref(null)
const inlineDestId = ref(null)
const vFocus = { mounted: el => el.focus() }

const showManual  = ref(false)
const editMode    = ref(false)
const saving      = ref(false)
const formError   = ref('')

const txAttachments      = ref([])
const attachmentUploading = ref(false)

const emptyForm = () => ({
  date: new Date().toISOString().slice(0,10),
  amount: '',
  description: '',
  accountId: '',
  categoryId: '',
  destination: 'family',
  paidByPersonId: '',
  splitPersonId: '',
  splitPercent: 50,
  isCash: false,
  isReimbursable: false,
  reimbursementAmount: '',
  notes: '',
  _id: null,
})
const form = ref(emptyForm())

// ── Computed ──────────────────────────────────────────
const filtered = computed(() => {
  let list = transactions.value
  if (filterText.value) {
    const q = filterText.value.toLowerCase()
    list = list.filter(t =>
      (t.merchant_name || '').toLowerCase().includes(q) ||
      (t.description_raw || '').toLowerCase().includes(q)
    )
  }
  if (filterAccount.value) list = list.filter(t => t.account_id === Number(filterAccount.value))
  if (filterCategory.value) list = list.filter(t => t.category_id === Number(filterCategory.value))
  if (filterDest.value) {
    const [dest, personId] = filterDest.value.split(':')
    list = list.filter(t => t.destination === dest && (!personId || t.paid_by_person_id === Number(personId)))
  }
  if (filterReimb.value === 'pending')    list = list.filter(t => t.is_reimbursable && !t.reimbursed_at)
  if (filterReimb.value === 'reimbursed') list = list.filter(t => t.is_reimbursable && t.reimbursed_at)
  if (filterConfirmed.value === 'pending')   list = list.filter(t => !t.is_confirmed)
  if (filterConfirmed.value === 'confirmed') list = list.filter(t => t.is_confirmed)
  const dir = sortDir.value === 'asc' ? 1 : -1
  const key = sortKey.value
  return [...list].sort((a, b) => {
    const av = a[key], bv = b[key]
    if (av < bv) return -1 * dir
    if (av > bv) return 1 * dir
    return 0
  })
})

const allSelected = computed(() => filtered.value.length > 0 && filtered.value.every(t => selectedIds.value.has(t.id)))

// Le categorie disattivate non vengono piu' proposte nei menu di scelta: se
// pero' si sta modificando una transazione gia' assegnata a una categoria nel
// frattempo disattivata, quella resta comunque selezionabile per non perderla.
// type 'opening_balance' e' la categoria di sistema usata solo dal checkpoint
// annuale di saldo iniziale (vedi Accounts.vue): non deve mai comparire come
// scelta manuale per categorizzare una transazione normale.
const activeCategories = computed(() => categories.value.filter(c => c.is_active && c.type !== 'opening_balance'))
const activeCategoriesTree = computed(() => sortCategoriesAsTree(activeCategories.value))
const formCategoryOptions = computed(() => {
  const current = categories.value.find(c => c.id === form.value.categoryId)
  if (current && !current.is_active) return [...activeCategories.value, current]
  return activeCategories.value
})
function categoryOptionsFor(tx) {
  const current = categories.value.find(c => c.id === tx.category_id)
  if (current && !current.is_active) return [...activeCategories.value, current]
  return activeCategories.value
}

const reimbursementAmountOf = t => t.reimbursement_amount != null ? t.reimbursement_amount : Math.abs(t.amount)

const totalPendingReimbursement = computed(() =>
  transactions.value
    .filter(t => t.is_reimbursable && !t.reimbursed_at)
    .reduce((sum, t) => sum + reimbursementAmountOf(t), 0)
)

const importAccount = computed(() => accounts.value.find(a => a.id === Number(importAccountId.value)))
const importAccountOwnership = computed(() => importAccount.value?.ownership || '')
const importAccountOwnerId = computed(() => importAccount.value?.owner_id || null)

// ── Formatters ────────────────────────────────────────
const fmt = v => new Intl.NumberFormat('it-IT', { style:'currency', currency:'EUR' }).format(v)
const categoryName = id => categories.value.find(c => c.id === id)?.name
const categoryIcon = id => categories.value.find(c => c.id === id)?.icon || '📌'
const accountName  = id => accounts.value.find(a => a.id === id)?.name || '—'
const personName   = id => persons.value.find(p => p.id === id)?.name || ''
const destLabel    = d => ({ family: t('transactions.destination.family'), personal: t('transactions.destination.personal'), split: t('transactions.destination.split') }[d] || d)

// Un conto personale segrega le sue spese: cambiando conto, la destinazione e
// l'intestatario si allineano di conseguenza (restano comunque modificabili).
function onAccountChange() {
  const acc = accounts.value.find(a => a.id === Number(form.value.accountId))
  if (!acc) return
  if (acc.ownership === 'personal') {
    form.value.destination = 'personal'
    form.value.paidByPersonId = acc.owner_id || ''
  } else {
    form.value.destination = 'family'
    form.value.paidByPersonId = ''
  }
}

// ── Load ─────────────────────────────────────────────
async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const params = {}
    if (filterMonth.value)   params.month       = filterMonth.value
    if (filterAccount.value) params.accountId   = filterAccount.value
    if (filterCategory.value) params.categoryId = filterCategory.value
    if (filterDest.value) {
      const [dest, personId] = filterDest.value.split(':')
      params.destination = dest
      if (personId) params.personId = personId
    }
    if (filterReimb.value)   params.reimbursable = filterReimb.value
    if (filterConfirmed.value === 'pending')   params.unconfirmed = 'true'
    if (filterConfirmed.value === 'confirmed') params.confirmed   = 'true'

    const qs = new URLSearchParams({ ...params, limit: 200 }).toString()
    const safe = p => p.catch(() => ({ data: [] }))
    const [txRes, catRes, accRes, pendRes, perRes] = await Promise.all([
      api.get(`api/transactions?${qs}`),
      safe(api.get('api/categories')),
      safe(api.get('api/accounts')),
      safe(api.get('api/transactions/pending-ai')),
      safe(api.get('api/persons')),
    ])
    transactions.value = Array.isArray(txRes.data) ? txRes.data : []
    total.value        = transactions.value.length
    categories.value   = Array.isArray(catRes.data) ? catRes.data : []
    accounts.value     = Array.isArray(accRes.data) ? accRes.data : []
    pendingAI.value    = Array.isArray(pendRes.data) ? pendRes.data : []
    persons.value      = Array.isArray(perRes.data)  ? perRes.data : []
  } catch (e) {
    loadError.value = e?.response?.data?.error || e.message || t('transactions.errors.loadFailed')
  } finally {
    loading.value = false
  }
}

// ── Confirm AI ────────────────────────────────────────
async function confirmAll() {
  const ids = pendingAI.value.map(t => t.id)
  await api.post('api/transactions/confirm-bulk', { ids })
  load()
}

// ── Selezione multipla / azioni di gruppo ─────────────
function toggleSelect(id) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = next
}

function toggleSelectAll() {
  if (allSelected.value) {
    selectedIds.value = new Set()
  } else {
    selectedIds.value = new Set(filtered.value.map(t => t.id))
  }
}

function clearSelection() {
  selectedIds.value = new Set()
  bulkForm.value = emptyBulkForm()
}

async function applyBulk() {
  const patch = {}
  if (bulkForm.value.categoryId !== '')     patch.categoryId = bulkForm.value.categoryId
  if (bulkForm.value.accountId !== '')      patch.accountId = bulkForm.value.accountId
  if (bulkForm.value.destination !== '')    patch.destination = bulkForm.value.destination
  if (bulkForm.value.paidByPersonId === '__clear__') patch.paidByPersonId = null
  else if (bulkForm.value.paidByPersonId !== '')     patch.paidByPersonId = bulkForm.value.paidByPersonId
  if (bulkForm.value.isReimbursable !== '') patch.isReimbursable = true
  if (!Object.keys(patch).length) return
  bulkApplying.value = true
  try {
    await api.post('api/transactions/bulk-update', { ids: [...selectedIds.value], ...patch })
    clearSelection()
    load()
  } catch (e) {
    alert(e?.response?.data?.error || t('transactions.errors.applyBulkFailed'))
  } finally {
    bulkApplying.value = false
  }
}

async function bulkConfirm() {
  bulkApplying.value = true
  try {
    await api.post('api/transactions/bulk-update', { ids: [...selectedIds.value], isConfirmed: true })
    clearSelection()
    load()
  } catch (e) {
    alert(e?.response?.data?.error || t('transactions.errors.confirmFailed'))
  } finally {
    bulkApplying.value = false
  }
}

async function bulkRejectAi() {
  bulkApplying.value = true
  try {
    await api.post('api/transactions/reject-ai-bulk', { ids: [...selectedIds.value] })
    clearSelection()
    load()
  } catch (e) {
    alert(e?.response?.data?.error || t('transactions.errors.rejectAiFailed'))
  } finally {
    bulkApplying.value = false
  }
}

async function bulkCategorizeAi() {
  bulkApplying.value = true
  try {
    const { data } = await api.post('api/transactions/categorize-ai', { ids: [...selectedIds.value] })
    clearSelection()
    load()
    if (!data.categorized) {
      alert(t('transactions.errors.noCategorySuggested'))
    }
  } catch (e) {
    alert(e?.response?.data?.error || t('transactions.errors.categorizeAiFailed'))
  } finally {
    bulkApplying.value = false
  }
}

async function bulkDelete() {
  if (!confirm(t('transactions.confirms.bulkDelete', { count: selectedIds.value.size }))) return
  bulkApplying.value = true
  try {
    await api.post('api/transactions/bulk-delete', { ids: [...selectedIds.value] })
    clearSelection()
    load()
  } catch (e) {
    alert(e?.response?.data?.error || t('transactions.errors.deleteFailed'))
  } finally {
    bulkApplying.value = false
  }
}

// ── Manual add/edit ───────────────────────────────────
function openManual() {
  form.value = emptyForm()
  editMode.value = false
  formError.value = ''
  txAttachments.value = []
  showManual.value = true
}

// ── Aggiungi spesa con AI ──────────────────────────────
const aiQuickText = ref('')
const aiQuickLoading = ref(false)
const aiQuickError = ref('')

// Non salva subito: precompila solo il form di inserimento manuale, che resta
// aperto per una revisione/conferma esplicita (stesso principio delle
// categorie suggerite dall'AI sugli import - mai fidarsi ciecamente).
async function aiQuickAdd() {
  const text = aiQuickText.value.trim()
  if (!text) return
  aiQuickLoading.value = true
  aiQuickError.value = ''
  try {
    const { data } = await api.post('api/transactions/ai-parse', { text })
    form.value = emptyForm()
    if (data.date) form.value.date = data.date
    if (data.amount != null) form.value.amount = -Math.abs(data.amount)
    form.value.description = data.description || text
    if (data.categoryId) form.value.categoryId = data.categoryId
    if (data.accountId) {
      form.value.accountId = data.accountId
      onAccountChange()
    }
    editMode.value = false
    formError.value = ''
    txAttachments.value = []
    showManual.value = true
    aiQuickText.value = ''
  } catch (e) {
    aiQuickError.value = e?.response?.data?.detail || e?.response?.data?.error || t('transactions.errors.aiParseFailed')
  } finally {
    aiQuickLoading.value = false
  }
}
function editTx(tx) {
  form.value = {
    date: tx.date,
    amount: tx.amount,
    description: tx.merchant_name || tx.description_raw || '',
    accountId: tx.account_id,
    categoryId: tx.category_id || '',
    destination: tx.destination || 'family',
    paidByPersonId: tx.paid_by_person_id || '',
    splitPersonId: tx.split_person_id || '',
    splitPercent: tx.split_ratio != null ? Math.round(tx.split_ratio * 100) : 50,
    isCash: !!tx.is_cash,
    isReimbursable: !!tx.is_reimbursable,
    reimbursementAmount: tx.reimbursement_amount != null ? tx.reimbursement_amount : '',
    notes: tx.notes || '',
    _id: tx.id,
  }
  editMode.value = true
  formError.value = ''
  loadAttachments(tx.id)
  showManual.value = true
}

function downloadUrl(documentId) {
  return new URL(`api/documents/${documentId}/download`, document.baseURI).toString()
}

async function loadAttachments(txId) {
  try {
    const res = await api.get(`api/documents?transactionId=${txId}`)
    txAttachments.value = Array.isArray(res.data) ? res.data : []
  } catch {
    txAttachments.value = []
  }
}

async function onAttachmentFileChange(e) {
  const file = e.target.files[0]
  e.target.value = ''
  if (!file || !form.value._id) return
  attachmentUploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    await api.post(`api/transactions/${form.value._id}/documents`, fd)
    loadAttachments(form.value._id)
  } catch (err) {
    alert(err?.response?.data?.error || t('transactions.errors.uploadAttachmentFailed'))
  } finally {
    attachmentUploading.value = false
  }
}

async function deleteAttachment(doc) {
  if (!confirm(t('transactions.confirms.removeAttachment', { filename: doc.filename }))) return
  try {
    await api.delete(`api/documents/${doc.id}`)
    loadAttachments(form.value._id)
  } catch (e) {
    alert(e?.response?.data?.error || t('transactions.errors.removeAttachmentFailed'))
  }
}

async function saveManual() {
  formError.value = ''
  if (!form.value.date || form.value.amount === '' || !form.value.description || !form.value.accountId) {
    formError.value = t('transactions.errors.requiredFields')
    return
  }
  if (form.value.destination === 'split' && !form.value.splitPersonId) {
    formError.value = t('transactions.errors.chooseSplitPerson')
    return
  }
  saving.value = true
  try {
    const { splitPercent, ...rest } = form.value
    const payload = {
      ...rest,
      amount: Number(form.value.amount),
      splitRatio: form.value.destination === 'split' ? (Number(splitPercent) || 50) / 100 : undefined,
      splitPersonId: form.value.destination === 'split' ? form.value.splitPersonId : null,
    }
    if (editMode.value && form.value._id) {
      await api.put(`api/transactions/${form.value._id}`, payload)
    } else {
      await api.post('api/transactions', payload)
    }
    showManual.value = false
    load()
  } catch(e) {
    formError.value = e?.response?.data?.error || e.message || t('transactions.errors.saveFailed')
  } finally {
    saving.value = false
  }
}

async function toggleReimbursed(tx) {
  try {
    await api.post(`api/transactions/${tx.id}/toggle-reimbursed`)
    load()
  } catch (e) {
    alert(e?.response?.data?.error || t('transactions.errors.toggleReimbursedFailed'))
  }
}

async function onInlineCategoryChange(tx, value) {
  const categoryId = value === '' ? null : Number(value)
  const previous = { category_id: tx.category_id, is_confirmed: tx.is_confirmed }
  inlineCategoryId.value = null
  tx.category_id = categoryId
  tx.is_confirmed = true
  try {
    await api.put(`api/transactions/${tx.id}`, { categoryId, isConfirmed: true })
  } catch (e) {
    tx.category_id = previous.category_id
    tx.is_confirmed = previous.is_confirmed
    alert(e?.response?.data?.error || t('transactions.errors.updateCategoryFailed'))
  }
}

async function onInlineDestChange(tx, value) {
  const previous = tx.destination
  inlineDestId.value = null
  tx.destination = value
  try {
    await api.put(`api/transactions/${tx.id}`, { destination: value })
  } catch (e) {
    tx.destination = previous
    alert(e?.response?.data?.error || t('transactions.errors.updateDestFailed'))
  }
}

async function confirmAiCategory(tx) {
  const previous = { category_id: tx.category_id, is_confirmed: tx.is_confirmed }
  tx.category_id = tx.ai_category_id
  tx.is_confirmed = true
  try {
    await api.put(`api/transactions/${tx.id}`, { categoryId: tx.ai_category_id, isConfirmed: true })
  } catch (e) {
    tx.category_id = previous.category_id
    tx.is_confirmed = previous.is_confirmed
    alert(e?.response?.data?.error || t('transactions.errors.confirmCategoryFailed'))
  }
}

async function deleteTx(tx) {
  if (!confirm(t('transactions.confirms.deleteTx', { name: tx.merchant_name || tx.description_raw }))) return
  await api.delete(`api/transactions/${tx.id}`)
  load()
}

// ── Import modal ──────────────────────────────────────
const importStreamStage = ref('')
const importStreamCount = ref(0)
const importStreamAccount = ref(null)

function closeImport() {
  showImport.value = false
  importStep.value = 'select'
  importFile.value = null
  importResult.value = {}
  importStreamStage.value = ''
  importStreamCount.value = 0
  importStreamAccount.value = null
  isDragover.value = false
}

function onFileChange(e) {
  const f = e.target.files[0]
  if (f) doImport(f)
}

// Le card CSV/Excel/PDF sono solo illustrative dei formati supportati, ma
// visivamente sembrano opzioni cliccabili (come i passi di un wizard): senza
// un click reale, cliccarle non fa nulla e sembra un bug all'utente. Aprono
// semplicemente lo stesso selettore file sotto, che gia' accetta tutti e tre
// i formati - non serve restringere l'accept per tipo, il backend riconosce
// il formato dall'estensione.
function pickFile() {
  fileInput.value?.click()
}

function onDrop(e) {
  isDragover.value = false
  const f = e.dataTransfer.files[0]
  if (f) doImport(f)
}

const fmtPreview = v => new Intl.NumberFormat('it-IT', { style:'currency', currency:'EUR' }).format(v)

async function doImport(file) {
  importFile.value = file
  importStep.value = 'loading'
  importStreamStage.value = ''
  importStreamCount.value = 0
  importStreamAccount.value = null

  if (file.name.toLowerCase().endsWith('.pdf')) {
    return doImportPdfStream(file)
  }

  try {
    const fd = new FormData()
    fd.append('file', file)
    if (importAccountId.value) fd.append('accountId', String(importAccountId.value))
    const res = await api.post('api/transactions/import', fd)
    importResult.value = res.data
    importStep.value = 'done'
    markedTransferIds.value = new Set()
    load()
  } catch(err) {
    importResult.value = { error: err?.response?.data?.error || err.message || t('transactions.errors.importFailed') }
    importStep.value = 'done'
  }
}

// Import PDF via SSE: mostra l'avanzamento (estrazione testo -> chiamata AI
// token per token -> analisi risposta) invece di un semplice spinner, perche'
// l'estrazione AI puo' richiedere 60-120s e senza feedback sembra bloccato.
function handleImportSseEvent(eventType, payload) {
  if (eventType === 'stage') {
    importStreamStage.value = payload.message
  } else if (eventType === 'progress') {
    importStreamCount.value = payload.count
  } else if (eventType === 'account') {
    importStreamAccount.value = payload
  } else if (eventType === 'error') {
    importResult.value = { error: payload.detail }
    importStep.value = 'done'
  } else if (eventType === 'done') {
    importResult.value = payload
    importStep.value = 'done'
    markedTransferIds.value = new Set()
    load()
  }
}

async function doImportPdfStream(file) {
  try {
    const fd = new FormData()
    fd.append('file', file)
    if (importAccountId.value) fd.append('accountId', String(importAccountId.value))

    const headers = {}
    const personId = getPersonId()
    if (personId) headers['X-Person-Id'] = personId

    const res = await fetch(new URL('api/transactions/import-pdf-stream', document.baseURI), {
      method: 'POST',
      body: fd,
      headers,
    })
    if (!res.ok || !res.body) throw new Error(t('transactions.errors.httpError', { status: res.status }))

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let streamDone = false
    while (!streamDone) {
      const { value, done } = await reader.read()
      streamDone = done
      if (value) buffer += decoder.decode(value, { stream: true })

      let sepIndex
      while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
        const rawEvent = buffer.slice(0, sepIndex)
        buffer = buffer.slice(sepIndex + 2)

        let eventType = 'message'
        let dataLine = ''
        for (const line of rawEvent.split('\n')) {
          if (line.startsWith('event:')) eventType = line.slice(6).trim()
          else if (line.startsWith('data:')) dataLine += line.slice(5).trim()
        }
        if (!dataLine) continue
        handleImportSseEvent(eventType, JSON.parse(dataLine))
      }
    }
  } catch (err) {
    importResult.value = { error: err.message || t('transactions.errors.importFailed') }
    importStep.value = 'done'
  }
}

// ── Suggerimenti pagamento carta di credito ───────────
const markedTransferIds = ref(new Set())

async function markAsTransfer(suggestion) {
  const transferCategory = categories.value.find(c => c.type === 'transfer')
  if (!transferCategory) { alert(t('transactions.errors.transferCategoryNotFound')); return }
  try {
    await api.put(`api/transactions/${suggestion.transactionId}`, { categoryId: transferCategory.id, isConfirmed: true })
    markedTransferIds.value = new Set([...markedTransferIds.value, suggestion.transactionId])
    load()
  } catch (e) {
    alert(e?.response?.data?.error || t('transactions.errors.transferFailed'))
  }
}

onMounted(load)
</script>

<style scoped>
.topbar { background:#fff; border-bottom:1px solid #DDD9D0; padding:0 28px; height:56px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10; }
.topbar-title { font-size:15px; font-weight:600; }
.topbar-meta  { font-size:12px; color:#9A938C; }
.topbar-actions { display:flex; gap:8px; }

.content { padding:28px; }

.btn { display:inline-flex; align-items:center; gap:6px; padding:7px 14px; font-size:13px; font-weight:500; cursor:pointer; border:1px solid #DDD9D0; background:#fff; color:#5C5752; }
.btn:disabled { opacity:.5; cursor:not-allowed; }
.btn-primary { background:#1D3557; color:#fff; border-color:#1D3557; }
.btn-teal    { background:#2A9D8F; color:#fff; border-color:#2A9D8F; }
.btn-danger  { background:#E76F51; color:#fff; border-color:#E76F51; }
.btn-sm      { padding:5px 10px; font-size:12px; }
.btn-icon    { width:28px; height:28px; border:1px solid #DDD9D0; background:#fff; cursor:pointer; font-size:12px; display:grid; place-items:center; }
.btn-icon.danger:hover { background:#FCF0EC; border-color:#E76F51; color:#E76F51; }

.ai-quick-add { display:flex; align-items:center; gap:8px; margin-bottom:16px; }
.ai-quick-input { flex:1; max-width:420px; }
.ai-quick-error { font-size:12px; color:#E76F51; }
.ai-banner { background:#EBF0F6; border:1px solid #1D3557; padding:12px 16px; display:flex; align-items:center; justify-content:space-between; margin-bottom:16px; font-size:13px; color:#1D3557; }
.reimb-banner { background:#FCF0EC; border:1px solid #E76F51; padding:12px 16px; display:flex; align-items:center; justify-content:space-between; margin-bottom:16px; font-size:13px; color:#E76F51; }
.bulk-bar { background:#FEF5E7; border:1px solid #E8A020; padding:10px 16px; display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:16px; }
.bulk-count { font-size:12.5px; font-weight:600; color:#5C5752; margin-right:4px; }
.input-sm { padding:6px 8px; font-size:12px; width:auto; }
.bulk-bar .cat-picker { min-width:170px; }

.filters { display:flex; gap:8px; margin-bottom:16px; flex-wrap:wrap; }
.filter-input { min-width:160px; flex:1; }
.filter-sel   { min-width:140px; }
.input { padding:8px 11px; border:1px solid #DDD9D0; background:#F7F6F2; font-size:13px; font-family:inherit; outline:none; }
.input:focus  { border-color:#1D3557; background:#fff; }

.tx-list { background:#fff; border:1px solid #DDD9D0; }
.tx-header { display:grid; grid-template-columns:20px 32px 85px 1fr 130px 90px 70px 90px 100px 56px; padding:10px 16px; background:#F0EEE9; font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:#9A938C; border-bottom:1px solid #DDD9D0; gap:12px; }
.tx-person { font-size:11px; color:#5C5752; font-weight:500; }
.tx-row    { display:grid; grid-template-columns:20px 32px 85px 1fr 130px 90px 70px 90px 100px 56px; padding:11px 16px; border-bottom:1px solid #DDD9D0; gap:12px; align-items:center; }
.tx-date   { font-size:12px; color:#5C5752; font-variant-numeric:tabular-nums; }
.sortable  { cursor:pointer; user-select:none; }
.sortable:hover { color:#1D3557; }
.sort-arrow { margin-left:3px; }
.tx-row:last-child { border-bottom:none; }
.tx-row:hover { background:#F7F6F2; }
.tx-row.pending { background:#FEF5E7; }
.tx-icon { width:28px; height:28px; display:grid; place-items:center; font-size:14px; background:#F0EEE9; }
.tx-name   { font-size:13px; font-weight:500; }
.tx-desc   { font-size:11px; color:#9A938C; margin-top:1px; }
.tx-links  { display:flex; gap:8px; margin-top:3px; }
.tx-link   { display:inline-flex; align-items:center; gap:2px; font-size:11px; color:#5C5752; background:none; border:none; padding:0; cursor:pointer; text-decoration:none; font-family:inherit; }
.tx-link:hover { color:#1D3557; }
.tx-amount { font-size:13.5px; font-weight:500; text-align:right; font-variant-numeric:tabular-nums; }
.tx-amount.neg { color:#E76F51; }
.tx-amount.pos { color:#2A9D8F; }
.tx-acc    { font-size:11px; color:#9A938C; text-align:right; }
.tx-actions { display:flex; gap:4px; }
.chip { display:inline-flex; align-items:center; gap:3px; padding:3px 8px; font-size:11px; background:#F0EEE9; color:#5C5752; }
.chip-editable { cursor:pointer; }
.chip-editable:hover { outline:1px solid #1D3557; }
.tx-cat-cell { display:flex; align-items:center; gap:6px; }
.tx-cat-cell .cat-picker { flex:1; min-width:0; }
.btn-icon-mini { width:20px; height:20px; flex-shrink:0; border:1px solid #2A9D8F; background:#E6F5F3; color:#2A9D8F; cursor:pointer; font-size:11px; display:grid; place-items:center; padding:0; }
.btn-icon-mini:hover { background:#2A9D8F; color:#fff; }
.chip-ai       { background:#EBF0F6; color:#1D3557; }
.chip-family   { background:#E6F5F3; color:#2A9D8F; }
.chip-personal { background:#FEF5E7; color:#E8A020; }
.chip-split    { background:#F3E9F6; color:#7B2D8B; }
.chip-reimb      { background:#FCF0EC; color:#E76F51; }
.chip-reimb-done { background:#E6F5F3; color:#2A9D8F; }
.tx-dest-cell { display:flex; flex-direction:column; gap:3px; align-items:flex-start; }
.empty { text-align:center; padding:40px; color:#9A938C; font-size:13px; }
.error-msg { color:#E76F51; }
.num { font-variant-numeric:tabular-nums; }

/* Modal */
.modal-backdrop { position:fixed; inset:0; background:rgba(0,0,0,.35); z-index:100; display:grid; place-items:center; }
.modal { background:#fff; width:540px; max-width:95vw; max-height:90vh; display:flex; flex-direction:column; border:1px solid #DDD9D0; }
.modal-header { padding:16px 20px; border-bottom:1px solid #DDD9D0; display:flex; justify-content:space-between; align-items:center; font-size:14px; font-weight:600; }
.modal-body   { padding:20px; overflow-y:auto; display:flex; flex-direction:column; gap:14px; }
.modal-footer { padding:16px 20px; border-top:1px solid #DDD9D0; display:flex; justify-content:flex-end; align-items:center; gap:8px; }
.form-row     { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
.form-group   { display:flex; flex-direction:column; gap:6px; }
.label        { font-size:12px; font-weight:500; color:#5C5752; }
.check        { display:flex; align-items:center; gap:6px; font-size:13px; cursor:pointer; }
.form-error   { font-size:12px; color:#E76F51; flex:1; }
.attachment-list { display:flex; flex-direction:column; gap:6px; margin-bottom:8px; }
.attachment-row { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:6px 10px; background:#F7F6F2; border:1px solid #DDD9D0; }
.attachment-name { font-size:12.5px; color:#1D3557; text-decoration:none; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.attachment-name:hover { text-decoration:underline; }
.attachment-upload { cursor:pointer; display:inline-flex; width:fit-content; }

/* Import modal */
.modal-import { width:600px; }
.import-formats { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
.format-card { padding:14px; border:1px solid #DDD9D0; text-align:center; cursor:pointer; }
.format-card:hover { border-color:#1D3557; background:#F7F9FB; }
.format-card.ai-badge { border-color:#1D3557; background:#EBF0F6; }
.format-icon { font-size:22px; margin-bottom:6px; }
.format-name { font-size:13px; font-weight:600; }
.format-desc { font-size:11px; color:#9A938C; margin-top:3px; }
.ai-tag { background:#1D3557; color:#fff; font-size:10px; padding:1px 5px; vertical-align:middle; }

.upload-zone { display:flex; flex-direction:column; align-items:center; justify-content:center; gap:6px;
  border:2px dashed #DDD9D0; padding:32px; margin-top:16px; cursor:pointer; transition:border-color .15s; }
.upload-zone:hover, .upload-zone.dragover { border-color:#1D3557; background:#EBF0F6; }
.upload-icon { font-size:28px; color:#9A938C; }
.upload-text { font-size:13px; color:#5C5752; }
.link { color:#1D3557; text-decoration:underline; }
.upload-hint { font-size:11px; color:#9A938C; }
.import-hint { font-size:11px; color:#E8A020; margin-top:6px; }

.modal-center { display:flex; flex-direction:column; align-items:center; gap:16px; padding:40px; }
.spinner { width:36px; height:36px; border:3px solid #DDD9D0; border-top-color:#1D3557; border-radius:50%; animation:spin .8s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
.loading-text { text-align:center; font-size:13px; color:#5C5752; display:flex; flex-direction:column; gap:4px; }
.hint-ai { font-size:11px; color:#1D3557; margin-top:4px; }

.result-badge { display:flex; gap:14px; align-items:flex-start; padding:16px; border:1px solid; margin-bottom:12px; }
.result-ok  { background:#E6F5F3; border-color:#2A9D8F; color:#2A9D8F; }
.result-err { background:#FCF0EC; border-color:#E76F51; color:#E76F51; }
.result-icon { font-size:20px; font-weight:700; flex-shrink:0; }
.result-title { font-size:14px; font-weight:600; }
.result-sub { font-size:12px; margin-top:3px; opacity:.8; }

.preview-list { border:1px solid #DDD9D0; }
.preview-header { padding:8px 12px; background:#F0EEE9; font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:#9A938C; }
.preview-row { display:grid; grid-template-columns:90px 1fr 90px; padding:8px 12px; border-top:1px solid #DDD9D0; font-size:12px; gap:8px; align-items:center; }
.preview-date { font-variant-numeric:tabular-nums; color:#9A938C; }
.preview-desc { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.preview-amount { text-align:right; font-weight:500; font-variant-numeric:tabular-nums; }
.preview-amount.neg { color:#E76F51; }
.preview-amount.pos { color:#2A9D8F; }
.info-box { padding:10px 14px; background:#EBF0F6; border:1px solid #1D3557; font-size:12px; color:#1D3557; line-height:1.6; }
.warning-box { margin-top:12px; padding:10px 14px; background:#FCF0EC; border:1px solid #E76F51; font-size:12px; color:#8a3a2a; line-height:1.6; }

.transfer-suggestions { border:1px solid #E8A020; margin-top:12px; }
.suggestion-row { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:10px 12px; border-top:1px solid #F0EEE9; font-size:12.5px; }
.suggestion-sub { font-size:11px; color:#9A938C; margin-top:2px; }
</style>
