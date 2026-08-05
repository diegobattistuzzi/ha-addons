# Spese di casa (CasaSpese)

Add-on Home Assistant per la gestione delle spese familiari: import estratti conto (CSV, PDF), categorizzazione automatica con AI, budget mensili/annuali per categoria, visibilità per persona, sensori HA e ricevute via email.

> Nota storica: il progetto è nato con un backend Node.js/Fastify (vedi `SPEC.md`, non più aggiornata); da metà 2026 il backend attivo è **Python/FastAPI** (`backend/server.py`). La cartella `backend/src` è il vecchio backend Node dismesso, tenuta solo per riferimento.

## Stack

| Layer | Tecnologia |
| --- | --- |
| Backend | Python 3.12, **FastAPI** + Uvicorn, SQLite |
| Frontend | Vue 3 + Vite, servito come SPA statica dal backend |
| AI | OpenAI o Anthropic (chiave configurabile), fallback `ai_task` di Home Assistant |
| Add-on | Docker, `config.yaml` standard Home Assistant, ingress |

## Funzionalità principali

- **Conti e persone**: conti condivisi/personali, con visibilità delle transazioni "personali" limitata al proprietario (`backend/access.py`).
- **Import transazioni**: CSV/XLSX con rilevamento automatico delle colonne, estratti PDF (anche a due colonne, causali multi-riga, estratti carta di credito) — `backend/statement_parsing.py`, `backend/pdf_import.py`.
- **Categorizzazione automatica**: regole utente (pattern/regex su descrizione + segno importo, priorità, possono anche impostare destinazione/persona e auto-confermare) → riconoscimento giroconti tra conti propri via IBAN → parole chiave per categoria → fallback AI (OpenAI/Anthropic o `ai_task` di Home Assistant se l'add-on gira senza chiave propria) — `backend/routers/rules.py`, `backend/categorize.py`.
- **Budget per categoria**: soglia mensile e annuale (`categories.budget_monthly` / `budget_annual`), con avviso nei report e nei sensori quando sforati.
- **Ricevute via email**: backfill IMAP storico + arricchimento automatico delle transazioni con mail di conferma acquisto (PayPal, Amazon, ecc.) — `backend/email_backfill.py`, `backend/email_enrich.py`.
- **Assistente AI**: riepilogo narrativo mensile, rilevamento anomalie di spesa (picchi per categoria, nuovi esercenti) e una chat conversazionale per costruire/salvare report personalizzati — `backend/ai_reports.py`, `frontend/src/views/Assistant.vue`.
- **Integrazione Home Assistant**: sensori REST (`/api/ha/sensors`), riconoscimento utente via ingress, import automatico delle persone da `person.*`.
- **Server MCP**: espone in sola lettura conti/transazioni/report a client MCP (es. Claude) su `/mcp`, autenticato con lo stesso token mobile della PWA — `backend/mcp_server.py`.
- **Backup**: export/import completo in Excel (`backend/backup.py`).

## Struttura del progetto

```text
gestionecontabile/
├── config.yaml           # Manifest add-on Home Assistant (opzioni, schema, ingress)
├── Dockerfile             # Multi-stage: build frontend (Node) + runtime Python
├── docker-compose.yml     # Solo sviluppo locale
├── deploy-addon.ps1       # Copia i sorgenti sulla share \\...\addons\ di HA
├── backend/
│   ├── server.py          # Entry point FastAPI: app, middleware, mount dei router e del server MCP
│   ├── routers/           # Route REST per dominio (accounts, transactions, categories, persons,
│   │                      # reports, rules, documents, email_receipts, ha, ai, setup, system)
│   ├── config.py          # Opzioni add-on (da /data/options.json) + env locali
│   ├── db.py              # Connessione SQLite
│   ├── migrate.py         # Schema + migrazioni idempotenti + categorie di default
│   ├── access.py          # Visibilità conti/transazioni per persona
│   ├── ai_client.py       # Wrapper OpenAI/Anthropic/ai_task
│   ├── categorize.py      # Regole utente + parole chiave + fallback AI per categorizzare le transazioni
│   ├── ai_reports.py      # Riepilogo narrativo mensile e rilevamento anomalie (Assistente AI)
│   ├── mcp_server.py      # Server MCP (sola lettura) montato su /mcp
│   ├── pdf_import.py      # Parsing estratti conto PDF
│   ├── statement_parsing.py  # Parsing estratti conto CSV/XLSX
│   ├── email_backfill.py  # Backfill storico IMAP per persona
│   ├── email_enrich.py    # Estrazione AI + matching ricevute email -> transazioni
│   ├── email_poller.py    # Polling periodico della casella IMAP in background
│   ├── backup.py          # Export/import Excel
│   ├── requirements.txt
│   └── src/                # (dismesso) vecchio backend Node.js/Fastify
└── frontend/
    ├── src/views/          # Dashboard, Transactions, Accounts, Categories, Rules, Reports, Assistant, ...
    └── src/views/setup/    # Wizard di primo avvio
```

## Sviluppo locale

Prerequisiti: Python 3.12+, Node 22+.

```bash
npm run install:all   # pip install backend + npm install frontend
npm run dev            # avvia uvicorn --reload (8099) + vite dev server, in parallelo
```

In locale (fuori da Home Assistant) creare `data/options.json` da `data/options.json.example` con la chiave AI, oppure usare le variabili d'ambiente in `.env` (vedi `.env.example`).

Build del frontend per servirlo direttamente dal backend Python:

```bash
npm run build --prefix frontend    # oppure: cd frontend && npm run build:local
```

## Deploy sull'add-on Home Assistant

```powershell
./deploy-addon.ps1                 # copia verso \\192.168.1.56\addons\gestionecontabile
./deploy-addon.ps1 -DryRun         # simula, senza copiare nulla
./deploy-addon.ps1 -Mirror         # copia e rimuove sul target i file non più presenti in origine
```

Dopo la copia, ricostruisci l'add-on da *Impostazioni → Add-on → Spese di casa* in Home Assistant.

## Configurazione (config.yaml)

| Opzione | Descrizione |
| --- | --- |
| `ai_provider` / `ai_model` | Provider e modello AI per la categorizzazione |
| `openai_api_key` / `anthropic_api_key` | Chiave del provider scelto |
| `sync_interval_minutes` | Frequenza del controllo automatico della casella IMAP per le ricevute via email |
| `ha_token` | Token per chiamate autenticate verso l'API di Home Assistant |
| `public_url` | URL pubblico https (dietro il reverse proxy nginx) usato per generare il link/QR di accesso mobile — vedi sotto |

Richiede `homeassistant_api: true` per l'accesso a `person.*` e agli utenti HA.

## Accesso mobile (PWA) e scansione scontrini

Oltre all'uso da dentro Home Assistant (Ingress), l'app è installabile come PWA
su cellulare per fotografare uno scontrino (OCR via AI vision), scegliere
contanti/conto personale e salvare la spesa. L'accesso è per-persona: da
**Persone → 📱 "Accesso mobile"** si genera un token e un QR/link da aprire sul
telefono (`Persons.vue`, `POST /api/mobile-tokens`).

**Importante**: l'Ingress di Home Assistant non è raggiungibile da fuori la
rete locale, quindi per l'uso da cellulare serve esporre l'app anche fuori
dalla LAN. Due modi equivalenti per farlo, scegli quello che preferisci —
cambia solo *come* internet raggiunge nginx, non cosa fa nginx:

- **A. Porta pubblica sul router** — port-forward diretto verso nginx, con
  DNS (o DDNS se IP dinamico) e certificato TLS (es. Let's Encrypt) gestiti
  da te.
- **B. Cloudflare Tunnel** — riusa il tunnel già attivo per l'accesso remoto
  a HA (add-on `c50d1fa4-cloudflare-tunnel`): niente porta aperta sul router,
  niente DNS/certificato da mantenere, TLS terminato da Cloudflare. In cambio
  dipendi dal servizio Cloudflare.

In entrambi i casi resta **obbligatorio** un reverse proxy locale (nginx) che
ripulisca gli header in ingresso — questo non lo fa né il router né il
tunnel, va fatto sempre a mano.

Passi comuni a entrambe le opzioni:

1. In *Impostazioni → Add-on → Spese di casa → Rete*, assegna un host-port
   alla mappatura `8099/tcp` dichiarata in `config.yaml` (`ports`). Questo
   espone il container su quella porta dell'host **oltre** all'Ingress
   esistente, che resta invariato.
2. Configura nginx con una `location`/vhost dedicata che fa da reverse proxy
   verso `127.0.0.1:<porta scelta>`. **Non** esporre mai quella porta
   direttamente su internet: deve passare sempre da nginx. In quella vhost,
   nginx **deve** rimuovere/sovrascrivere questi header in ingresso —
   **obbligatorio**, non opzionale, altrimenti l'app resta completamente
   aperta a chiunque su internet senza alcun token:

   ```nginx
   location / {
       proxy_pass http://127.0.0.1:<porta scelta>;
       proxy_set_header X-Remote-User-Id "";
       proxy_set_header X-Person-Id "";
       proxy_set_header X-Ingress-Path "";
       proxy_set_header Host $host;
       proxy_set_header X-Forwarded-Proto $scheme;
   }
   ```

   Il backend (`backend/server.py:enforce_public_gateway_auth`) blocca con 401
   ogni chiamata `/api/*` che non provenga dall'Ingress di HA (riconosciuto
   dall'header `X-Ingress-Path`, impostato solo dal Supervisor) **e** non porti
   un token mobile valido — ma questo protegge solo se `X-Ingress-Path` non può
   essere falsificato da un client esterno, cioè solo se nginx lo azzera come
   sopra. Lo stesso vale per `X-Remote-User-Id`/`X-Person-Id`, usati altrove
   per riconoscere la persona (vedi il commento in
   `backend/access.py:get_current_person`): senza questa pulizia, un client
   esterno potrebbe impostare lui stesso uno di questi header e impersonare
   sia l'Ingress genuino sia una persona qualsiasi.

Poi, a seconda dell'opzione scelta:

- **A. Porta pubblica**: configura la vhost nginx in HTTPS (certificato
  proprio) e fai il port-forward sul router verso quella vhost. `X-Forwarded-Proto`
  sopra resta `$scheme` (nginx vede direttamente il client).
- **B. Cloudflare Tunnel**: la vhost nginx può restare in HTTP semplice (il
  TLS verso internet lo fa Cloudflare) — in tal caso sostituisci
  `proxy_set_header X-Forwarded-Proto $scheme;` con
  `proxy_set_header X-Forwarded-Proto "https";`. Nel tunnel aggiungi un
  secondo hostname pubblico (es. `spese.tuodominio.it`, stesso dominio già
  usato per HA) con service `http://<ip-lan-host>:<porta scelta>` (IP LAN
  dell'host dove gira nginx, non `localhost`: il tunnel è un add-on separato
  e non condivide il network namespace). Se il tunnel è **remote-managed**
  (token, gestito dalla dashboard Zero Trust anziché da un `config.yml`
  locale), questo hostname va aggiunto nella dashboard Cloudflare — in quel
  caso la configurazione dell'add-on viene ignorata a parte il token.

Infine, indipendentemente dall'opzione scelta:

1. Imposta l'opzione add-on `public_url` con l'URL pubblico completo (es.
   `https://spese.tuodominio.it`): serve solo per comporre il link nel QR.
2. Genera il primo accesso da **Persone → 📱**, inquadra il QR dal cellulare
   e installa la PWA ("Aggiungi a schermata Home").

Un token può essere revocato in qualsiasi momento dalla stessa schermata
(`DELETE /api/mobile-tokens/{id}`): il dispositivo perde subito l'accesso.
