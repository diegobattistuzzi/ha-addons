# CasaSpese — Specifica Tecnica v1.0

> Addon Home Assistant per la gestione delle spese familiari con AI e Open Banking PSD2.

---

## 1. Contesto e obiettivi

### Utenti
- **Coppia** (Sara + Marco) con conti comuni e conti personali separati
- Possibile estensione futura a famiglie più numerose

### Obiettivo principale
Avere una visione unificata e automatizzata delle spese familiari, senza dover aprire ogni singola app bancaria, con categorizzazione AI e report chiari su chi deve cosa a chi.

### Non-obiettivi (v1)
- Gestione investimenti / portafoglio
- Previsioni di spesa ML (future release)
- Multi-household

---

## 2. Stack tecnologico

| Layer | Tecnologia | Note |
|---|---|---|
| **Backend** | Node.js 22 LTS + **Fastify 5** | L'utente viene da JS |
| **ORM / DB** | **Drizzle ORM** + SQLite (better-sqlite3) | Embedded, zero-config, backup semplice |
| **AI** | **OpenAI API** (gpt-4o-mini) o **Anthropic** (claude-haiku) | Configurabile da UI — ~€0.50/mese |
| **Open Banking** | **GoCardless/Nordigen API** (PSD2) | Gratuito fino a 50 req/giorno, copre tutte le banche target |
| **Parser PDF** | **pdf-parse** + **tabula-js** | Per estratti PDF |
| **Parser CSV** | **csv-parse** + schema-detection AI | Rileva colonne automaticamente |
| **Frontend** | **Vue 3** + **Vite** + **Tailwind CSS** | SPA servita da Fastify |
| **HA Addon** | **Docker** (node:22-alpine) | config.yaml standard HA |
| **HA Integration** | REST API + WebSocket | Sensori, binary_sensor, servizi |

### Banche supportate (v1)
- Fineco Bank (CSV + PDF)
- ING Italia (CSV)
- N26 (CSV — include Spaces)
- Revolut (CSV)
- Wise (CSV)
- Hello Bank (CSV + PDF)
- Generica via AI schema detection (fallback per qualsiasi banca)

---

## 3. Architettura del progetto

```
casaspese/
├── config.yaml              # Manifest Home Assistant Addon
├── Dockerfile
├── docker-compose.yml       # Solo per sviluppo locale
│
├── backend/
│   ├── package.json
│   ├── src/
│   │   ├── server.js        # Fastify entry point
│   │   ├── config.js        # Variabili ambiente + validazione
│   │   │
│   │   ├── db/
│   │   │   ├── schema.js    # Drizzle schema definitions
│   │   │   ├── migrate.js   # Migrations runner
│   │   │   └── index.js     # DB singleton
│   │   │
│   │   ├── routes/
│   │   │   ├── accounts.js       # CRUD conti
│   │   │   ├── transactions.js   # CRUD transazioni + upload
│   │   │   ├── categories.js     # CRUD categorie + budget
│   │   │   ├── persons.js        # CRUD persone
│   │   │   ├── reports.js        # Aggregazioni e report
│   │   │   ├── banksync.js       # GoCardless endpoints
│   │   │   ├── setup.js          # Setup wizard endpoints
│   │   │   └── ha.js             # Home Assistant webhook/sensori
│   │   │
│   │   ├── services/
│   │   │   ├── ai/
│   │   │   │   ├── categorizer.js    # Categorizzazione batch con AI
│   │   │   │   ├── schemaDetector.js # Rileva formato CSV/PDF
│   │   │   │   └── insights.js       # Analisi anomalie e suggerimenti
│   │   │   │
│   │   │   ├── parsers/
│   │   │   │   ├── base.js           # Interface comune parser
│   │   │   │   ├── fineco.js
│   │   │   │   ├── ing.js
│   │   │   │   ├── n26.js
│   │   │   │   ├── revolut.js
│   │   │   │   ├── wise.js
│   │   │   │   ├── hellobank.js
│   │   │   │   ├── pdfParser.js      # Estratti PDF generici
│   │   │   │   └── generic.js        # Fallback AI-driven
│   │   │   │
│   │   │   ├── banksync/
│   │   │   │   ├── nordigen.js       # GoCardless/Nordigen client
│   │   │   │   ├── scheduler.js      # Cron sync automatico
│   │   │   │   └── reconciler.js     # Dedup + merge transazioni
│   │   │   │
│   │   │   ├── ha/
│   │   │   │   ├── sensors.js        # Aggiorna sensori HA
│   │   │   │   └── webhooks.js       # Gestione webhook in entrata
│   │   │   │
│   │   │   └── reports/
│   │   │       ├── monthly.js        # Report mensile
│   │   │       ├── balance.js        # Saldo tra persone
│   │   │       └── subscriptions.js  # Rilevamento abbonamenti
│   │   │
│   │   └── utils/
│   │       ├── dedup.js          # Fuzzy dedup transazioni
│   │       ├── currency.js       # Formattazione valuta
│   │       └── logger.js         # Structured logging
│   │
└── frontend/
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── main.js
        ├── App.vue
        ├── router.js
        │
        ├── views/
        │   ├── Dashboard.vue
        │   ├── Transactions.vue
        │   ├── Reports.vue
        │   ├── BankSync.vue
        │   └── setup/
        │       ├── SetupWizard.vue
        │       ├── StepPersons.vue
        │       ├── StepAccounts.vue
        │       ├── StepCategories.vue
        │       └── StepApiKeys.vue
        │
        ├── components/
        │   ├── TransactionRow.vue
        │   ├── BudgetBar.vue
        │   ├── AiSuggestion.vue
        │   ├── UploadZone.vue
        │   ├── DonutChart.vue
        │   ├── TrendChart.vue
        │   └── BalanceSplit.vue
        │
        └── stores/           # Pinia stores
            ├── transactions.js
            ├── accounts.js
            ├── categories.js
            └── reports.js
```

---

## 4. Schema database (Drizzle + SQLite)

### persons
```js
{
  id:         integer PK autoincrement,
  name:       text NOT NULL,
  email:      text,
  color:      text,           // hex color per UI
  is_primary: integer,        // boolean
  created_at: text
}
```

### accounts
```js
{
  id:           integer PK autoincrement,
  name:         text NOT NULL,
  bank:         text,          // 'fineco'|'ing'|'n26'|'revolut'|'wise'|'hellobank'|'cash'|'other'
  type:         text,          // 'checking'|'savings'|'credit_card'|'prepaid'|'cash'
  ownership:    text,          // 'shared'|'personal'
  owner_id:     integer FK persons,   // null se shared
  co_owners:    text,          // JSON array di person IDs se shared
  iban:         text,
  color:        text,
  nordigen_id:  text,          // ID conto su GoCardless
  last_sync_at: text,
  balance:      real,
  is_active:    integer,
  created_at:   text
}
```

### categories
```js
{
  id:           integer PK autoincrement,
  name:         text NOT NULL,
  icon:         text,          // emoji
  color:        text,
  parent_id:    integer FK categories,  // per sottocategorie future
  budget_monthly: real,
  type:         text,          // 'expense'|'income'|'transfer'
  ai_keywords:  text,          // JSON array — hint per AI
  sort_order:   integer,
  is_active:    integer
}
```

### transactions
```js
{
  id:              integer PK autoincrement,
  date:            text NOT NULL,         // ISO 8601
  amount:          real NOT NULL,         // positivo=entrata, negativo=uscita
  currency:        text DEFAULT 'EUR',
  description_raw: text,                  // testo originale dalla banca
  merchant_name:   text,                  // estratto/normalizzato da AI
  merchant_category_code: text,           // MCC se disponibile (Open Banking)
  category_id:     integer FK categories,
  account_id:      integer FK accounts NOT NULL,
  destination:     text,                  // 'family'|'personal'|'split'
  split_person_id: integer FK persons,    // chi ha fatto la spesa personale
  split_ratio:     real,                  // es. 0.5 per 50/50 (default 1.0)
  space_name:      text,                  // N26 Spaces o simili
  is_cash:         integer DEFAULT 0,
  ai_category_id:  integer FK categories, // suggerimento AI (prima di conferma)
  ai_confidence:   real,                  // 0.0–1.0
  is_confirmed:    integer DEFAULT 0,     // utente ha confermato categoria
  import_hash:     text UNIQUE,           // per dedup: sha256(date+amount+description)
  import_source:   text,                  // 'nordigen'|'csv'|'pdf'|'manual'
  import_batch_id: text,                  // raggruppamento per upload
  reimbursement_of: integer FK transactions,  // collegamento rimborsi
  notes:           text,
  created_at:      text,
  updated_at:      text
}
```

### budgets (override mensile per categoria)
```js
{
  id:          integer PK autoincrement,
  category_id: integer FK categories,
  year_month:  text,           // '2026-06'
  amount:      real,
  created_at:  text
}
```

### bank_sync_log
```js
{
  id:          integer PK autoincrement,
  account_id:  integer FK accounts,
  synced_at:   text,
  tx_fetched:  integer,
  tx_new:      integer,
  tx_duplicate:integer,
  error:       text,
  duration_ms: integer
}
```

### settings (chiave-valore)
```js
{
  key:   text PK,
  value: text           // JSON serializzato
}
// Chiavi:
// 'setup_completed', 'ai_provider', 'ai_model', 'sync_interval_minutes',
// 'default_currency', 'ha_webhook_token'
```

---

## 5. API REST (Fastify)

### Setup
```
GET  /api/setup/status          → { completed, step }
POST /api/setup/persons         → crea/aggiorna persone iniziali
POST /api/setup/accounts        → crea conti iniziali
POST /api/setup/categories      → attiva categorie predefinite
POST /api/setup/complete        → segna setup completato
```

### Persons
```
GET    /api/persons
POST   /api/persons
PUT    /api/persons/:id
DELETE /api/persons/:id
```

### Accounts
```
GET    /api/accounts
POST   /api/accounts
PUT    /api/accounts/:id
DELETE /api/accounts/:id
GET    /api/accounts/:id/balance
```

### Transactions
```
GET    /api/transactions          ?month=2026-06&account=&category=&destination=&unconfirmed=true
GET    /api/transactions/:id
POST   /api/transactions          (inserimento manuale / contante)
PUT    /api/transactions/:id
DELETE /api/transactions/:id
POST   /api/transactions/import   (upload file: multipart/form-data)
GET    /api/transactions/import/:batchId/preview   → anteprima prima di salvare
POST   /api/transactions/import/:batchId/confirm
POST   /api/transactions/confirm-bulk   { ids: [...] }
GET    /api/transactions/pending-ai     → da confermare
```

### Categories
```
GET    /api/categories
POST   /api/categories
PUT    /api/categories/:id
DELETE /api/categories/:id
GET    /api/categories/defaults   → lista preset
```

### Reports
```
GET /api/reports/summary?month=2026-06
    → { total_expenses, total_income, by_category[], by_person[], budget_status[] }

GET /api/reports/trend?months=6
    → { months[], family[], personal[], budget }

GET /api/reports/balance?month=2026-06
    → { person1_owes, person2_owes, net_amount, detail[] }

GET /api/reports/subscriptions
    → { subscriptions[], total_monthly }

POST /api/reports/balance/:month/settle
    → segna mese come saldato
```

### Bank Sync (GoCardless/Nordigen)
```
GET  /api/banksync/status
GET  /api/banksync/banks               → lista banche supportate con search
POST /api/banksync/connect             { bank_id, account_id } → redirect URL
GET  /api/banksync/callback            (OAuth callback da Nordigen)
POST /api/banksync/sync                → sync manuale tutti i conti
POST /api/banksync/sync/:accountId     → sync manuale singolo conto
GET  /api/banksync/log?limit=50
```

### Home Assistant
```
GET  /api/ha/sensors                   → stato corrente tutti i sensori
POST /api/ha/webhook                   → riceve eventi da HA
```

---

## 6. Servizio AI — categorizzazione

### Flusso
```
Upload/Sync
    ↓
Parse transazioni raw
    ↓
Dedup (import_hash)
    ↓
Batch categorization AI (max 50 tx per chiamata)
    ↓
Salva con ai_category_id + ai_confidence + is_confirmed=false
    ↓
UI mostra pending → utente approva/corregge
    ↓
is_confirmed=true, category_id = confermata
```

### Prompt AI (categorizzazione)
```
Sei un assistente per la gestione spese familiari italiane.
Categorizza le seguenti transazioni bancarie.
Categorie disponibili: [lista con id e keywords]
Per ogni transazione fornisci: category_id, confidence (0-1), merchant_name normalizzato.

Transazioni:
[{ id, description, amount, date }, ...]

Rispondi SOLO con JSON array: [{ id, category_id, confidence, merchant_name }]
```

### Modello consigliato
- `gpt-4o-mini` — ottimo rapporto qualità/costo per categorizzazione
- Costo stimato: ~100 transazioni/mese × $0.00015 = < $0.02/mese
- Fallback: `claude-haiku-4-5` se provider = Anthropic

### AI Insights (settimanale, schedulato)
Analisi separata per:
1. Rilevamento abbonamenti (pattern ricorrenti stessa cifra stesso merchant)
2. Anomalie (spesa categoria > 2σ dalla media)
3. Ottimizzazione (servizi duplicati, abbonamenti inutilizzati)

---

## 7. Parser estratti conto

### Strategia
```
1. Ricevi file (CSV o PDF)
2. Rileva banca:
   a. Da filename pattern  ("Fineco_estratto_*.csv")
   b. Da intestazione CSV  (header column names)
   c. Da contenuto PDF     (nome banca nel documento)
   d. Fallback: AI schema detection (invia prime 5 righe → AI identifica colonne)
3. Applica parser specifico
4. Output normalizzato: Transaction[]
5. Preview all'utente prima del save
```

### Formato normalizzato output parser
```js
{
  date: '2026-06-25',        // ISO
  amount: -87.40,            // negativo = uscita
  description_raw: 'PAGAMENTO POS ESSELUNGA MILANO',
  merchant_hint: 'Esselunga',
  account_hint: 'Fineco',    // per matching con account in DB
}
```

### Deduplicazione
`import_hash = sha256(date + '|' + Math.abs(amount).toFixed(2) + '|' + description_raw.trim().toLowerCase())`

Se hash già presente in DB → skip silenzioso, conteggiato in `tx_duplicate`.

---

## 8. Bank Sync — GoCardless/Nordigen

### Flusso connessione nuovo conto
```
1. Utente sceglie banca dalla lista (GET /api/banksync/banks)
2. Backend chiama Nordigen: POST /api/v2/requisitions/
   { institution_id, redirect, reference }
3. Utente viene reindirizzato al link di autenticazione banca
4. Dopo auth, Nordigen chiama il nostro callback
5. Backend salva nordigen_id sull'account
6. Prima sincronizzazione automatica
```

### Flusso sync periodico
```
Ogni N minuti (configurabile, default 30):
  Per ogni account con nordigen_id:
    GET /api/v2/accounts/{id}/transactions/?date_from=yesterday
    → Normalizza → Dedup → Categorizza AI → Salva pending
    → Aggiorna sensori HA
```

### Token management
- Access token: durata 24h, salvato in settings
- Refresh token: durata 30 giorni
- Requisition (accesso conto): durata 90-180 giorni → notify utente prima della scadenza

### Banche italiane supportate da Nordigen
| Banca | institution_id |
|---|---|
| Fineco | `FINECO_FEBIITM1` |
| ING Italia | `ING_INGBNL2A` |
| Hello Bank (BNP) | `BNP_BNPAITRRXXX` |
| UniCredit | `UNICREDIT_UNCRITMM` |
| BancoPosta | `POSTE_BNLIITRR` |
| N26 | `N26_NTSBDEB1` |
| Revolut | `REVOLUT_REVOGB21` |
| Wise | `WISE_TRWIGB22` |

---

## 9. Home Assistant Integration

### Sensori esposti (REST API polling da HA)
```yaml
sensor.casaspese_spese_mese:
  state: 2847.30
  attributes: { month: "2026-06", currency: "EUR" }

sensor.casaspese_budget_residuo:
  state: 652.70
  attributes: { total_budget: 3500, percent_used: 81 }

sensor.casaspese_saldo_comuni:
  state: 6240.00
  attributes: { accounts: [{name, balance}] }

sensor.casaspese_dare_avere:
  state: 127.50
  attributes: { debtor: "Marco", creditor: "Sara" }

sensor.casaspese_spese_oggi:
  state: 145.90

binary_sensor.casaspese_budget_ok:
  state: false    # true se nessuna categoria sforata
  attributes: { over_budget: ["Casa & Utenze", "Ristoranti"] }

binary_sensor.casaspese_sync_ok:
  state: true
  attributes: { last_sync: "2026-06-27T09:41:03" }

binary_sensor.casaspese_pending_review:
  state: true
  attributes: { count: 12 }
```

### Servizi HA
```yaml
casaspese.sync:           # forza sincronizzazione
casaspese.add_expense:    # aggiunge spesa manuale
  fields: { amount, category, description, account_id }
casaspese.approve_pending: # approva tutte le pendenti
```

### Notifiche (via notify service)
- Budget categoria sforato → notify immediato
- Abbonamento inutilizzato rilevato → notify settimanale
- Token banca in scadenza → notify 7gg prima
- Spesa anomala (>2σ) → notify real-time

### Configurazione HA (configuration.yaml)
```yaml
rest:
  - scan_interval: 300
    resource: http://localhost:8099/api/ha/sensors
    sensor:
      - name: "CasaSpese Spese Mese"
        value_template: "{{ value_json.spese_mese }}"
```

---

## 10. Addon Home Assistant

### config.yaml
```yaml
name: CasaSpese
version: "1.0.0"
slug: casaspese
description: Gestione spese familiari con AI e Open Banking
url: https://github.com/user/casaspese-addon
arch: [aarch64, amd64, armhf, armv7, i386]
startup: application
boot: auto
ingress: true
ingress_port: 8099
panel_icon: mdi:wallet-outline
panel_title: CasaSpese
map:
  - config:rw
  - data:rw
options:
  openai_api_key: ""
  nordigen_secret_id: ""
  nordigen_secret_key: ""
  sync_interval_minutes: 30
  ha_token: ""
schema:
  openai_api_key: str
  nordigen_secret_id: str
  nordigen_secret_key: str
  sync_interval_minutes: int(5, 1440)
  ha_token: str
```

### Dockerfile
```dockerfile
FROM node:22-alpine
WORKDIR /app
COPY backend/package*.json ./backend/
COPY frontend/package*.json ./frontend/
RUN cd backend && npm ci --production
RUN cd frontend && npm ci
COPY . .
RUN cd frontend && npm run build
# frontend build → backend/public/
ENV NODE_ENV=production
ENV PORT=8099
CMD ["node", "backend/src/server.js"]
```

---

## 11. Fasi di sviluppo

### Fase 0 — Bootstrap (1-2h)
- [ ] `npm create` backend Fastify + frontend Vue
- [ ] Drizzle schema + prima migration
- [ ] Dockerfile + config.yaml HA
- [ ] Hot-reload setup per sviluppo

### Fase 1 — Core CRUD (2-3h)
- [ ] Setup wizard (4 step)
- [ ] CRUD persone, conti, categorie
- [ ] Inserimento manuale transazione / contante

### Fase 2 — Import file (3-4h)
- [ ] Upload endpoint + multipart
- [ ] Parser Fineco CSV
- [ ] Parser ING CSV
- [ ] Parser generico AI (schema detection)
- [ ] Preview + conferma import
- [ ] Deduplicazione

### Fase 3 — AI categorizzazione (2h)
- [ ] OpenAI client con retry
- [ ] Batch categorizer
- [ ] UI revisione pending
- [ ] Approva/correggi singolo e bulk

### Fase 4 — Report e Dashboard (3h)
- [ ] API report mensile + trend
- [ ] Donut chart spese
- [ ] Budget bars con override
- [ ] Saldo dare/avere
- [ ] Rilevamento abbonamenti

### Fase 5 — Bank Sync (3-4h)
- [ ] GoCardless client
- [ ] Flusso OAuth + callback
- [ ] Scheduler sync automatico
- [ ] Log sincronizzazione
- [ ] Notifica scadenza token

### Fase 6 — Home Assistant (2h)
- [ ] Endpoint sensori
- [ ] Servizi HA
- [ ] Notifiche su eventi
- [ ] Documentazione YAML per configuration.yaml

### Fase 7 — AI Insights (2h)
- [ ] Rilevamento abbonamenti
- [ ] Anomaly detection
- [ ] Suggerimenti UI

---

## 12. Variabili d'ambiente

```env
# Runtime (da HA addon options o .env locale)
PORT=8099
DATA_DIR=/data                   # montato da HA, contiene casaspese.db
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...     # alternativa
AI_PROVIDER=openai               # 'openai'|'anthropic'|'ollama'
AI_MODEL=gpt-4o-mini
NORDIGEN_SECRET_ID=...
NORDIGEN_SECRET_KEY=...
SYNC_INTERVAL_MINUTES=30
HA_TOKEN=...                     # long-lived access token HA
HA_BASE_URL=http://homeassistant:8123
NODE_ENV=production
```

---

## 13. Decisioni architetturali e motivazioni

| Decisione | Alternativa scartata | Motivazione |
|---|---|---|
| SQLite + Drizzle | PostgreSQL, MySQL | Zero-config per addon HA, backup è un file, sufficiente per uso familiare |
| Fastify | Express | Validazione schema built-in, più performante, plugin system moderno |
| GoCardless/Nordigen | Plaid, Salt Edge | Gratuito fino a 50 req/giorno, copre banche italiane target, PSD2 compliance |
| gpt-4o-mini | gpt-4o, claude-opus | Costo irrisorio per categorizzazione semplice, qualità più che sufficiente |
| Vue 3 | React, Svelte | Preferenza utente (JS background), Composition API moderna |
| Import con preview | Import diretto | Permette correzione prima del commit, evita dati sporchi |
| hash-based dedup | ID-based | Non tutte le banche forniscono ID transazione, l'hash è universale |

---

*Documento generato: 2026-06-27*
*Versione: 1.0 — da aggiornare durante lo sviluppo*
