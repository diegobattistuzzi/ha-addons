import json
import sqlite3
from .db import conn

CATEGORIES_VERSION = 2
DEFAULT_CATEGORIES = [
    {'code':'AG',   'name':'Spese bimbe',           'icon':'👧', 'color':'#E8A020', 'type':'expense', 'sort_order':1,  'ai_keywords': json.dumps(['bimbe','bambine','agatha','anita','asilo','scuola','giocattoli'])},
    {'code':'AN',   'name':'AN',                     'icon':'📌', 'color':'#9A938C', 'type':'expense', 'sort_order':2,  'ai_keywords': json.dumps([])},
    {'code':'VA',   'name':'Vestiti Agatha e Anita', 'icon':'👗', 'color':'#E8A020', 'type':'expense', 'sort_order':3,  'ai_keywords': json.dumps(['zara kids','h&m kids','okaidi','abbigliamento bambini'])},
    {'code':'VC',   'name':'Vestiti Anita',          'icon':'👚', 'color':'#A8DADC', 'type':'expense', 'sort_order':4,  'ai_keywords': json.dumps(['vestiti anita'])},
    {'code':'CL',   'name':'Spesa Cloe',             'icon':'🐾', 'color':'#E76F51', 'type':'expense', 'sort_order':5,  'ai_keywords': json.dumps(['cloe','veterinario','petshop','crocchette'])},
    {'code':'RE',   'name':'Regali',                 'icon':'🎁', 'color':'#7B2D8B', 'type':'expense', 'sort_order':6,  'ai_keywords': json.dumps(['regalo','regali','fiori'])},
    {'code':'AP',   'name':'Appartamento',           'icon':'🏠', 'color':'#1D3557', 'type':'expense', 'sort_order':10, 'ai_keywords': json.dumps(['affitto','mutuo','condominio','agenzia'])},
    {'code':'SN',   'name':'Spesa casa nuova',       'icon':'🛋️', 'color':'#457B9D', 'type':'expense', 'sort_order':11, 'ai_keywords': json.dumps(['ikea','leroy merlin','obi','bricocenter','casa nuova'])},
    {'code':'EN',   'name':'Enel',                   'icon':'⚡', 'color':'#E8A020', 'type':'expense', 'sort_order':12, 'ai_keywords': json.dumps(['enel','luce','elettricità','energia elettrica'])},
    {'code':'GAS',  'name':'Gas',                    'icon':'🔥', 'color':'#E76F51', 'type':'expense', 'sort_order':13, 'ai_keywords': json.dumps(['gas','eni gas','italgas','snam'])},
    {'code':'TEL',  'name':'Telefono',               'icon':'📱', 'color':'#457B9D', 'type':'expense', 'sort_order':14, 'ai_keywords': json.dumps(['tim','vodafone','wind','fastweb','iliad','telefono','internet'])},
    {'code':'TAX',  'name':'Tasse',                  'icon':'🧾', 'color':'#9A938C', 'type':'expense', 'sort_order':15, 'ai_keywords': json.dumps(['agenzia entrate','imu','tari','bollo','f24','tassa','imposta'])},
    {'code':'SA',   'name':'Spese alimentari',       'icon':'🛒', 'color':'#2A9D8F', 'type':'expense', 'sort_order':20, 'ai_keywords': json.dumps(['supermercato','esselunga','carrefour','lidl','conad','coop','pam','iper','eurospin','despar','bennet'])},
    {'code':'SG',   'name':'Spesa',                  'icon':'🛍️', 'color':'#2A9D8F', 'type':'expense', 'sort_order':21, 'ai_keywords': json.dumps(['spesa','market','alimentari','frutta','verdura'])},
    {'code':'P1',   'name':'Colazioni',              'icon':'☕', 'color':'#E8A020', 'type':'expense', 'sort_order':25, 'ai_keywords': json.dumps(['bar','caffè','colazione','cornetto','cappuccino'])},
    {'code':'P2',   'name':'Pranzi',                 'icon':'🍽️', 'color':'#E76F51', 'type':'expense', 'sort_order':26, 'ai_keywords': json.dumps(['pranzo','mensa','ristorante','trattoria','pizzeria','poke','sushi','just eat','deliveroo','glovo'])},
    {'code':'P3',   'name':'Cene',                   'icon':'🍷', 'color':'#7B2D8B', 'type':'expense', 'sort_order':27, 'ai_keywords': json.dumps(['cena','ristorante','pizzeria','osteria','trattoria'])},
    {'code':'P4',   'name':'Aperitivi',              'icon':'🍸', 'color':'#E76F51', 'type':'expense', 'sort_order':28, 'ai_keywords': json.dumps(['aperitivo','spritz','bar','cocktail','happy hour'])},
    {'code':'ING',  'name':'Ingressi',               'icon':'🎟️', 'color':'#E8A020', 'type':'expense', 'sort_order':29, 'ai_keywords': json.dumps(['museo','cinema','teatro','concerto','parco','biglietto','ticketone'])},
    {'code':'T1',   'name':'Peugeot',                'icon':'🚗', 'color':'#457B9D', 'type':'expense', 'sort_order':30, 'ai_keywords': json.dumps(['peugeot','carburante','benzina','gasolio','bollo auto','assicurazione auto','parcheggio','autostrada'])},
    {'code':'T2',   'name':'Auris',                  'icon':'🚙', 'color':'#1D3557', 'type':'expense', 'sort_order':31, 'ai_keywords': json.dumps(['auris','toyota','carburante','benzina','gasolio'])},
    {'code':'MF',   'name':'Farmacia',               'icon':'💊', 'color':'#2A9D8F', 'type':'expense', 'sort_order':35, 'ai_keywords': json.dumps(['farmacia','farmaco','medicinale','parafarmacia'])},
    {'code':'MV',   'name':'Visite',                 'icon':'🏥', 'color':'#2A9D8F', 'type':'expense', 'sort_order':36, 'ai_keywords': json.dumps(['medico','dottore','dentista','ospedale','clinica','analisi','visita','fisioterapia','pediatra'])},
    {'code':'FE',   'name':'Ferie',                  'icon':'✈️', 'color':'#457B9D', 'type':'expense', 'sort_order':40, 'ai_keywords': json.dumps(['hotel','airbnb','booking','expedia','volo','ryanair','easyjet','trenitalia','vacanza','ferie','agriturismo'])},
    {'code':'LD',   'name':'Lavoro Diego',           'icon':'💼', 'color':'#1D3557', 'type':'income',  'sort_order':50, 'ai_keywords': json.dumps(['stipendio diego','accredito stipendio','cedolino','busta paga'])},
    {'code':'LE',   'name':'Lavoro Erika',           'icon':'💼', 'color':'#2A9D8F', 'type':'income',  'sort_order':51, 'ai_keywords': json.dumps(['stipendio erika','accredito stipendio','cedolino','busta paga'])},
    {'code':'RIMB', 'name':'Rimborsi spese',         'icon':'↩️', 'color':'#2A9D8F', 'type':'income',  'sort_order':52, 'ai_keywords': json.dumps(['rimborso','restituzione','accredito','nota spese'])},
    {'code':'TRF',  'name':'Trasferimenti',          'icon':'↔️', 'color':'#9A938C', 'type':'transfer','sort_order':90, 'ai_keywords': json.dumps(['giroconto','trasferimento','tra conti'])},
    {'code':'ALT',  'name':'Altro',                  'icon':'📌', 'color':'#9A938C', 'type':'expense',  'sort_order':99, 'ai_keywords': json.dumps([])},
]


def _execute(statement, params=None):
    cursor = conn.cursor()
    cursor.execute(statement, params or ())
    return cursor


def run_migrations():
    statements = [
        '''CREATE TABLE IF NOT EXISTS persons (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             name TEXT NOT NULL,
             email TEXT,
             color TEXT DEFAULT '#1D3557',
             is_primary INTEGER DEFAULT 0,
             created_at TEXT DEFAULT (datetime('now'))
           )''',
        '''CREATE TABLE IF NOT EXISTS accounts (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             name TEXT NOT NULL,
             bank TEXT NOT NULL DEFAULT 'other',
             type TEXT NOT NULL DEFAULT 'checking',
             ownership TEXT NOT NULL DEFAULT 'shared',
             owner_id INTEGER REFERENCES persons(id),
             co_owners TEXT,
             iban TEXT,
             color TEXT,
             balance REAL,
             is_active INTEGER DEFAULT 1,
             created_at TEXT DEFAULT (datetime('now'))
           )''',
        '''CREATE TABLE IF NOT EXISTS categories (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             code TEXT,
             name TEXT NOT NULL,
             icon TEXT,
             color TEXT,
             parent_id INTEGER,
             budget_monthly REAL,
             type TEXT NOT NULL DEFAULT 'expense',
             ai_keywords TEXT,
             sort_order INTEGER DEFAULT 0,
             is_active INTEGER DEFAULT 1
           )''',
        '''CREATE TABLE IF NOT EXISTS transactions (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             date TEXT NOT NULL,
             amount REAL NOT NULL,
             currency TEXT DEFAULT 'EUR',
             description_raw TEXT,
             merchant_name TEXT,
             merchant_category_code TEXT,
             category_id INTEGER REFERENCES categories(id),
             account_id INTEGER NOT NULL REFERENCES accounts(id),
             destination TEXT DEFAULT 'family',
             paid_by_person_id INTEGER REFERENCES persons(id),
             split_person_id INTEGER REFERENCES persons(id),
             split_ratio REAL DEFAULT 1.0,
             space_name TEXT,
             is_cash INTEGER DEFAULT 0,
             ai_category_id INTEGER REFERENCES categories(id),
             ai_confidence REAL,
             is_confirmed INTEGER DEFAULT 0,
             import_hash TEXT UNIQUE,
             import_source TEXT DEFAULT 'manual',
             import_batch_id TEXT,
             reimbursement_of INTEGER,
             notes TEXT,
             created_at TEXT DEFAULT (datetime('now')),
             updated_at TEXT DEFAULT (datetime('now'))
           )''',
        '''CREATE TABLE IF NOT EXISTS budgets (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             category_id INTEGER NOT NULL REFERENCES categories(id),
             year_month TEXT NOT NULL,
             amount REAL NOT NULL,
             created_at TEXT DEFAULT (datetime('now')),
             UNIQUE(category_id, year_month)
           )''',
        '''CREATE TABLE IF NOT EXISTS settings (
             key TEXT PRIMARY KEY,
             value TEXT
           )''',
        '''CREATE TABLE IF NOT EXISTS documents (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             filename TEXT NOT NULL,
             stored_path TEXT NOT NULL,
             mime_type TEXT,
             size_bytes INTEGER,
             account_id INTEGER REFERENCES accounts(id),
             import_batch_id TEXT,
             uploaded_at TEXT DEFAULT (datetime('now'))
           )''',
        '''CREATE TABLE IF NOT EXISTS email_receipts (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             sender TEXT,
             subject TEXT,
             merchant TEXT,
             amount REAL,
             date TEXT,
             item_description TEXT,
             matched_transaction_id INTEGER REFERENCES transactions(id),
             received_at TEXT DEFAULT (datetime('now'))
           )''',
        # Ricetta di estrazione PDF (regex + formato data + segno) gia' validata
        # in passato per un conto/banca (vedi pdf_import.get_cached_recipe):
        # riusata prima di richiamare l'AI, cosi' un conto importato piu' volte
        # non ripaga ogni volta il costo di "ricapire" lo stesso formato.
        '''CREATE TABLE IF NOT EXISTS pdf_import_recipes (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             cache_key TEXT NOT NULL UNIQUE,
             bank_name TEXT,
             recipe_json TEXT NOT NULL,
             last_validated_at TEXT DEFAULT (datetime('now')),
             created_at TEXT DEFAULT (datetime('now')),
             updated_at TEXT DEFAULT (datetime('now'))
           )''',
        # Configurazione di un report personalizzato (dimensioni, filtri,
        # metrica, tipo di grafico) salvata come blob opaco: evita di dover
        # fare un'altra migrazione ogni volta che il builder guadagna
        # un'opzione in piu'.
        '''CREATE TABLE IF NOT EXISTS saved_reports (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             name TEXT NOT NULL,
             config_json TEXT NOT NULL,
             created_at TEXT DEFAULT (datetime('now')),
             updated_at TEXT DEFAULT (datetime('now'))
           )''',
        # Token di accesso per la PWA mobile: uno per persona (o piu', con
        # label diverse per piu' dispositivi). Si salva solo l'hash, mai il
        # token in chiaro - il valore grezzo viene mostrato una sola volta
        # alla creazione (nel QR/link) e non e' piu' recuperabile.
        '''CREATE TABLE IF NOT EXISTS mobile_tokens (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             person_id INTEGER NOT NULL REFERENCES persons(id),
             token_hash TEXT NOT NULL UNIQUE,
             label TEXT,
             created_at TEXT DEFAULT (datetime('now')),
             last_used_at TEXT,
             revoked_at TEXT
           )''',
        'CREATE INDEX IF NOT EXISTS idx_mobile_tokens_person ON mobile_tokens(person_id)',
        'CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date)',
        'CREATE INDEX IF NOT EXISTS idx_tx_account ON transactions(account_id)',
        'CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category_id)',
        'CREATE INDEX IF NOT EXISTS idx_tx_confirmed ON transactions(is_confirmed)',
        'CREATE INDEX IF NOT EXISTS idx_tx_amount ON transactions(amount)',
        'CREATE INDEX IF NOT EXISTS idx_documents_account ON documents(account_id)',
        'CREATE INDEX IF NOT EXISTS idx_documents_batch ON documents(import_batch_id)',
        'CREATE INDEX IF NOT EXISTS idx_email_receipts_matched ON email_receipts(matched_transaction_id)',
        # Coppie di transazioni gia' esaminate e giudicate NON duplicate
        # dall'utente (vedi GET /api/transactions/duplicates): sempre inserite
        # con transaction_id_a < transaction_id_b (normalizzato lato Python)
        # cosi' l'UNIQUE funziona indipendentemente dall'ordine in cui la
        # coppia viene ritrovata da una scansione successiva.
        '''CREATE TABLE IF NOT EXISTS transaction_dedup_dismissals (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             transaction_id_a INTEGER NOT NULL,
             transaction_id_b INTEGER NOT NULL,
             dismissed_at TEXT DEFAULT (datetime('now')),
             UNIQUE(transaction_id_a, transaction_id_b)
           )''',
        # Regole utente per riconoscere automaticamente le transazioni in
        # import (vedi categorize.py, valutate PRIMA delle keyword di
        # categoria/AI): a differenza delle keyword, una regola puo' impostare
        # anche destinazione/persona, non solo la categoria, e se matcha
        # conferma subito la transazione (is_confirmed=1) invece di lasciarla
        # come suggerimento AI da rivedere - e' una scelta esplicita
        # dell'utente, non un'ipotesi.
        '''CREATE TABLE IF NOT EXISTS import_rules (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             pattern TEXT NOT NULL,
             is_regex INTEGER DEFAULT 0,
             sign TEXT,
             category_id INTEGER NOT NULL REFERENCES categories(id),
             destination TEXT,
             paid_by_person_id INTEGER REFERENCES persons(id),
             split_person_id INTEGER REFERENCES persons(id),
             split_ratio REAL,
             priority INTEGER DEFAULT 0,
             is_active INTEGER DEFAULT 1,
             created_at TEXT DEFAULT (datetime('now'))
           )''',
        'CREATE INDEX IF NOT EXISTS idx_import_rules_active ON import_rules(is_active)',
        # Cronologia dell'assistente AI: una conversazione per thread di chat,
        # scoped per persona (a differenza di saved_reports) perche' le domande
        # fatte in chat possono riferirsi a dati personali dell'utente.
        '''CREATE TABLE IF NOT EXISTS ai_conversations (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             person_id INTEGER REFERENCES persons(id),
             title TEXT NOT NULL,
             created_at TEXT DEFAULT (datetime('now')),
             updated_at TEXT DEFAULT (datetime('now'))
           )''',
        '''CREATE TABLE IF NOT EXISTS ai_messages (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             conversation_id INTEGER NOT NULL REFERENCES ai_conversations(id),
             role TEXT NOT NULL,
             content TEXT NOT NULL,
             query_config_json TEXT,
             created_at TEXT DEFAULT (datetime('now'))
           )''',
        'CREATE INDEX IF NOT EXISTS idx_ai_conversations_person ON ai_conversations(person_id)',
        'CREATE INDEX IF NOT EXISTS idx_ai_messages_conversation ON ai_messages(conversation_id)',
    ]

    for stmt in statements:
        _execute(stmt)

    conn.commit()

    try:
        _execute('ALTER TABLE categories ADD COLUMN code TEXT')
    except sqlite3.OperationalError:
        pass

    try:
        _execute('ALTER TABLE transactions ADD COLUMN paid_by_person_id INTEGER REFERENCES persons(id)')
    except sqlite3.OperationalError:
        pass

    try:
        _execute('ALTER TABLE persons ADD COLUMN ha_user_id TEXT')
    except sqlite3.OperationalError:
        pass

    try:
        _execute('ALTER TABLE accounts ADD COLUMN settlement_account_id INTEGER REFERENCES accounts(id)')
    except sqlite3.OperationalError:
        pass

    try:
        _execute('ALTER TABLE transactions ADD COLUMN merchant_enriched INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass

    try:
        _execute('ALTER TABLE categories ADD COLUMN budget_annual REAL')
    except sqlite3.OperationalError:
        pass

    # Spese anticipate di tasca propria da richiedere a rimborso al datore di
    # lavoro: is_reimbursable le marca, reimbursed_at traccia quando l'azienda
    # ha effettivamente restituito i soldi.
    try:
        _execute('ALTER TABLE transactions ADD COLUMN is_reimbursable INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass

    try:
        _execute('ALTER TABLE transactions ADD COLUMN reimbursed_at TEXT')
    except sqlite3.OperationalError:
        pass

    # Importo effettivamente richiesto a rimborso: puo' differire dall'importo
    # della transazione (es. rimborso parziale). NULL = richiesto l'intero importo.
    try:
        _execute('ALTER TABLE transactions ADD COLUMN reimbursement_amount REAL')
    except sqlite3.OperationalError:
        pass

    # Collega la transazione al documento (estratto conto) da cui e' stata
    # importata: un documento genera molte transazioni (relazione 1-a-N), quindi
    # la FK sta sulla transazione, non sul documento.
    try:
        _execute('ALTER TABLE transactions ADD COLUMN document_id INTEGER REFERENCES documents(id)')
    except sqlite3.OperationalError:
        pass

    # Ultime cifre della carta associata al conto (per i conti type='credit_card'):
    # passate all'AI in pdf_import insieme a nome/IBAN dei conti noti, cosi'
    # riconosce a quale conto appartiene un rendiconto anche quando il numero
    # di carta e' mascherato in modo diverso da un documento all'altro.
    try:
        _execute('ALTER TABLE accounts ADD COLUMN card_number TEXT')
    except sqlite3.OperationalError:
        pass

    # Allegati caricati manualmente su una singola transazione (es. foto di uno
    # scontrino): qui la relazione e' inversa, un documento appartiene a una
    # sola transazione ma una transazione puo' avere piu' allegati.
    try:
        _execute('ALTER TABLE documents ADD COLUMN transaction_id INTEGER REFERENCES transactions(id)')
    except sqlite3.OperationalError:
        pass

    # Convenzione dei segni usata dall'estratto conto della carta (vedi
    # server.py parse_tabular_rows): l'euristica automatica assume che le
    # spese siano l'unica colonna importo sempre positiva, come nella
    # maggioranza dei rendiconti carta - ma American Express esporta gia' le
    # spese come negative e gli accrediti/storni come positivi, cioe' la
    # convenzione opposta e coerente con quella dell'app. Quando l'euristica
    # sbaglia per un istituto specifico, l'utente puo' fissare qui il
    # comportamento per quel conto invece di affidarsi al testo del
    # preambolo: 'auto' (default, euristica sul testo), 'flip' (spese sempre
    # positive nel file, da invertire), 'signed' (il file usa gia' il segno
    # giusto, non toccare nulla).
    try:
        _execute("ALTER TABLE accounts ADD COLUMN amount_sign_mode TEXT NOT NULL DEFAULT 'auto'")
    except sqlite3.OperationalError:
        pass

    # Data valuta (accredito/disponibilita' dei fondi), distinta dalla data
    # operazione gia' in 'date': serve a riconoscere meglio i doppioni quando
    # la stessa spesa arriva da fonti diverse con date leggermente diverse
    # (es. scontrino scansionato il giorno dell'acquisto vs. estratto conto
    # che riporta anche la valuta) - vedi GET /api/transactions/duplicates.
    try:
        _execute('ALTER TABLE transactions ADD COLUMN value_date TEXT')
    except sqlite3.OperationalError:
        pass

    _execute('CREATE INDEX IF NOT EXISTS idx_tx_document ON transactions(document_id)')
    _execute('CREATE INDEX IF NOT EXISTS idx_documents_transaction ON documents(transaction_id)')

    # Stato del controllo periodico automatico della casella IMAP (vedi
    # email_poller.py): imap_last_uid e' l'UID piu' alto gia' processato (per
    # leggere solo le mail nuove ad ogni giro, non l'intera cartella),
    # imap_uidvalidity rileva se il server ha "ricreato" la cartella (gli UID
    # vecchi perderebbero significato), imap_last_checked_at e' solo
    # informativo per mostrare in UI quando e' stato fatto l'ultimo controllo.
    for column, coltype in [
        ('imap_last_uid', 'INTEGER'),
        ('imap_uidvalidity', 'INTEGER'),
        ('imap_last_checked_at', 'TEXT'),
    ]:
        try:
            _execute(f'ALTER TABLE persons ADD COLUMN {column} {coltype}')
        except sqlite3.OperationalError:
            pass

    # Aggiunge le keyword 'booking'/'expedia' alla categoria Ferie sui DB gia'
    # esistenti, senza passare dal reseed completo legato a CATEGORIES_VERSION:
    # quel meccanismo cancella e reinserisce le categorie con nuovi id
    # autoincrement (sqlite non li riusa dopo una DELETE), il che orfanizzerebbe
    # silenziosamente category_id/ai_category_id di ogni transazione gia'
    # categorizzata - inaccettabile solo per aggiungere due parole chiave.
    # Aggiunge solo le keyword mancanti (non sovrascrive l'intera lista):
    # rispetta eventuali modifiche gia' fatte dall'utente in Impostazioni ->
    # Categorie. Il flag in settings evita di ripetere l'aggiunta ad ogni
    # avvio (altrimenti un utente che rimuove 'expedia' di proposito se la
    # ritroverebbe reinserita al riavvio successivo).
    if not _execute("SELECT value FROM settings WHERE key = 'fe_keywords_booking_expedia_added'").fetchone():
        fe_category = _execute("SELECT ai_keywords FROM categories WHERE code = 'FE'").fetchone()
        if fe_category is not None:
            keywords = json.loads(fe_category['ai_keywords'] or '[]')
            for kw in ('booking', 'expedia'):
                if kw not in keywords:
                    keywords.append(kw)
            _execute('UPDATE categories SET ai_keywords = ? WHERE code = ?', (json.dumps(keywords), 'FE'))
        _execute(
            'INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
            ('fe_keywords_booking_expedia_added', json.dumps(True)),
        )

    # Credenziali IMAP per il backfill storico delle mail di conferma
    # acquisto/pagamento (PayPal, Amazon, ...), salvate per persona: ognuno
    # usa la propria casella.
    for column, coltype in [
        ('imap_host', 'TEXT'),
        ('imap_port', 'INTEGER'),
        ('imap_username', 'TEXT'),
        ('imap_password', 'TEXT'),
        ('imap_use_ssl', 'INTEGER DEFAULT 1'),
        ('imap_folder', "TEXT DEFAULT 'INBOX'"),
    ]:
        try:
            _execute(f'ALTER TABLE persons ADD COLUMN {column} {coltype}')
        except sqlite3.OperationalError:
            pass

    version_row = _execute('SELECT value FROM settings WHERE key = ?', ('categories_version',)).fetchone()
    current_version = int(json.loads(version_row['value'])) if version_row else 0

    if current_version < CATEGORIES_VERSION:
        _execute('DELETE FROM categories')
        for cat in DEFAULT_CATEGORIES:
            _execute(
                'INSERT INTO categories (code, name, icon, color, type, sort_order, ai_keywords) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (cat['code'], cat['name'], cat['icon'], cat['color'], cat['type'], cat['sort_order'], cat['ai_keywords'])
            )
        _execute(
            'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
            ('categories_version', json.dumps(CATEGORIES_VERSION))
        )
        print(f'[migrate] Categorie aggiornate a v{CATEGORIES_VERSION}')

    # Categoria di sistema per i checkpoint di "saldo iniziale" annuale dei
    # conti (vedi _compute_account_balances in server.py): DEVE stare dopo il
    # blocco CATEGORIES_VERSION sopra, che fa DELETE FROM categories e
    # reinserisce solo DEFAULT_CATEGORIES - inserirla prima la farebbe
    # cancellare ad ogni reseed. Inserimento idempotente (fuori da
    # DEFAULT_CATEGORIES apposta, vedi commento su 'FE' piu' sopra).
    # is_active=0 e type='opening_balance' la tengono fuori dai tab
    # Spese/Entrate/Trasferimenti di Categories.vue e da qualunque
    # CategoryPicker usato per assegnare a mano una categoria a una spesa
    # normale.
    if not _execute("SELECT id FROM categories WHERE code = 'SALDO_INIT'").fetchone():
        _execute(
            'INSERT INTO categories (code, name, icon, color, type, sort_order, is_active) VALUES (?, ?, ?, ?, ?, ?, 0)',
            ('SALDO_INIT', 'Saldo iniziale', '🏁', '#9A938C', 'opening_balance', 999),
        )

    _execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('setup_completed', json.dumps(False)))
    conn.commit()
    print('[migrate] DB pronto')
