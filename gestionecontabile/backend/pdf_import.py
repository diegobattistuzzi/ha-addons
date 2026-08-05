import json
import re
from collections import Counter
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from dateutil.parser import parse as parse_date
from pypdf import PdfReader

from . import ai_client, db

# Quanto testo mandare all'AI per riconoscere il formato: bastano poche
# transazioni rappresentative, non serve l'intero estratto (che puo' avere
# centinaia di righe) - la ricetta risultante viene poi applicata a tutto il
# testo con un regex, in locale.
_SAMPLE_CHARS = 3500

# [ \t]? opzionale tra i gruppi (non solo dopo le prime 4 cifre): molti
# estratti/causali scrivono l'IBAN staccato in gruppi per leggibilita' (es.
# "IT72 S010 0512 5000 0000 0052 76") - senza tollerare gli spazi QUI il
# match falliva del tutto (niente da ripulire dopo, vedi _extract_iban che
# gia' fa re.sub(r'\s+', '', ...) sul risultato ma non trovava nessun match
# su cui applicarlo). Lo spazio opzionale e' ammesso solo ogni 1-4 caratteri
# (non prima di OGNI singolo carattere): con lo spazio ammesso ovunque il
# match si allungava a dismisura fino a inghiottire la prima parola normale
# dopo l'IBAN (uno spazio + lettere valide venivano lette come "altri
# caratteri dell'IBAN") - bug reale trovato testando su una causale reale
# tipo "IT72 ... causale varia", dove "causale" finiva dentro il match.
_IBAN_RE = re.compile(r'\b([A-Za-z]{2}[ \t]?\d{2}(?:[ \t]?[A-Za-z0-9]{1,4}){2,7})\b')
_CARD_RE = re.compile(r'[Cc]art[ae]\s*[Nn]?\.?\s*\*+\s*(\d{2,6})')
_DATE_TOKEN_RE = re.compile(r'\b\d{1,2}[/.]\d{1,2}[/.]\d{2,4}\b')

# Righe di saldo (apertura/chiusura periodo), non transazioni vere - bug reale
# trovato su un estratto ING/Conto Arancio dove "SALDO INIZIALE"/"SALDO
# FINALE" venivano importate come se fossero movimenti. Ancorato a INIZIO
# descrizione (non "in qualunque punto"): una transazione vera puo' avere
# "Saldo finale" incollato alla FINE della propria descrizione per un
# problema di lookahead non correlato (l'ultima transazione prima della fine
# pagina che non trova un confine pulito) - un match "search" generico la
# scarterebbe per sbaglio, bug reale trovato testando su un estratto Fineco.
# Fino a 10 caratteri non alfabetici tollerati a inizio riga (simboli valuta
# come "€" spesso decodificati male in caratteri di sostituzione "�" dalla
# decodifica di base di pypdf) prima di "SALDO INIZIALE/FINALE".
_BALANCE_SNAPSHOT_RE = re.compile(r'^[^a-zA-Z]{0,10}saldo\s+(iniziale|finale)\b', re.IGNORECASE)

# Riga di riepilogo a fine rendiconto carta di credito ("ADDEBITO IN C/C CON
# VALUTA gg.mm.aaaa"): e' il pagamento del saldo carta ricevuto dal conto
# corrente collegato, non un acquisto - bug reale trovato testando un
# rendiconto carta reale, dove veniva importata con segno negativo (la parola
# "addebito" la fa scambiare per una spesa) come se fosse un'ulteriore uscita,
# raddoppiando il totale gia' coperto dalla somma di tutte le righe reali.
# Sul CONTO CORRENTE questo stesso importo compare come una riga a se'
# (l'addebito carta vero e proprio): le due righe sono le due facce dello
# stesso trasferimento interno, quindi qui va importata positiva (riduce il
# debito verso la carta) e marcata come trasferimento (vedi isCardSettlement
# in extract_transactions_with_recipe/_normalize_direct_row e
# _finalize_import in server.py). Ancorato a INIZIO descrizione come
# _BALANCE_SNAPSHOT_RE, per lo stesso motivo.
_CARD_SETTLEMENT_RE = re.compile(r'^addebito\s+(in|su)\s+(c\s*/\s*c\b|conto\s+corrente\b)', re.IGNORECASE)

# Stessa riga di _CARD_SETTLEMENT_RE, ma cercata direttamente in TUTTO il
# testo invece che dentro una description gia' isolata dalla ricetta AI: bug
# reale trovato su un vero rendiconto BNL/Hello Card, dove questa riga
# appartiene alla tabella "RIEPILOGO OPERAZIONI" (il riepilogo, non il
# dettaglio movimenti) e ha una struttura DIVERSA dalle righe di
# DETTAGLIO OPERAZIONI (una sola data invece di due, nessun codice operazione
# numerico prima della descrizione) - la regex scritta dall'AI per il formato
# delle righe di dettaglio non la intercetta MAI. Non e' in una sezione
# fisicamente separata del documento: nel testo estratto compare dopo un
# cambio pagina con l'intestazione della tabella ripetuta (stesso artefatto
# di paginazione gia' gestito altrove da _strip_repeated_boilerplate), qui
# solo non abbastanza ripetuta da essere rimossa come boilerplate. Quindi qui
# non basta filtrare/correggere il segno DOPO il match della ricetta: va
# cercata con un pattern indipendente, come gia' si fa per IBAN (_IBAN_RE) e
# saldi di apertura/chiusura. La data di "valuta" (quando la banca preleva
# davvero dal conto corrente) e' piu' utile della data dell'operazione per
# abbinare questa riga alla corrispondente sul conto corrente, quindi e'
# preferita se presente.
_CARD_SETTLEMENT_LINE_RE = re.compile(
    r'^[ \t]*(?P<opdate>\d{1,2}[./]\d{1,2}[./]\d{2,4})[ \t]+addebito\s+(?:in|su)\s+(?:c\s*/\s*c|conto\s+corrente)\b'
    r'(?:[^\n]*?valuta[ \t]+(?P<valuta>\d{1,2}[./]\d{1,2}[./]\d{2,4}))?'
    r'[^\n]*?(?P<amount>\d{1,3}(?:[.,]\d{3})*[.,]\d{2})[ \t]*$',
    re.IGNORECASE | re.MULTILINE,
)

# Pattern "canonico" di un importo con separatore delle migliaia opzionale,
# usato per ri-leggere l'importo direttamente dal testo grezzo nella stessa
# posizione del gruppo (?P<amount>...) della ricetta: l'AI a volte scrive un
# gruppo importo troppo stretto (es. "-?\d{1,3}(?:[.,]\d{2})?", senza
# ripetizione delle migliaia), che su un importo come "1.031,32" cattura solo
# "1.03" - bug reale trovato su un estratto ING/Conto Arancio. Se questo
# pattern cattura PIU' caratteri del gruppo scritto dall'AI nella stessa
# posizione, usiamo il nostro risultato invece del suo.
_CANONICAL_AMOUNT_RE = re.compile(r'-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?')


_PAGE_NUMBER_RE = re.compile(r'^\s*pagina\s+\d+\s+di\s+\d+\s*$', re.IGNORECASE)
_CONTINUES_ON_PAGE_RE = re.compile(r'\bsegue\s+a\s+pagina\s+\d+\b', re.IGNORECASE)


def _strip_repeated_boilerplate(pages: List[str]) -> List[str]:
    """Le intestazioni/piè di pagina (indirizzo legale della banca, capitale
    sociale, ecc.) si ripetono IDENTICHE su ogni pagina del PDF. Quando una
    causale multiriga attraversa un cambio pagina, questo testo finisce dentro
    il gruppo description e fa perdere alla ricetta l'aggancio con l'inizio
    della transazione successiva, sballando le righe seguenti. Rimuoviamo le
    righe che compaiono su piu' pagine (qualunque banca, senza testo
    hardcoded) e i marcatori di paginazione tipo "Pagina 1 di 5" / "segue a
    pagina 2"."""
    if len(pages) < 2:
        return [_CONTINUES_ON_PAGE_RE.sub('', p) for p in pages]
    line_lists = [p.split('\n') for p in pages]
    counts = Counter()
    for lines in line_lists:
        for line in {l.strip() for l in lines if l.strip()}:
            counts[line] += 1
    threshold = max(2, len(pages) // 2)
    boilerplate = {line for line, c in counts.items() if c >= threshold and len(line) > 3}
    cleaned = []
    for lines in line_lists:
        kept = [
            l for l in lines
            if l.strip() not in boilerplate and not _PAGE_NUMBER_RE.match(l.strip())
        ]
        cleaned.append(_CONTINUES_ON_PAGE_RE.sub('', '\n'.join(kept)))
    return cleaned


def extract_pdf_text(data: bytes) -> str:
    """Usa il default 'plain' di pypdf, non 'layout': su un estratto conto
    reale (Fineco, testato) 'layout' produce output rotto - decine di righe
    vuote consecutive e contenuto spezzato su piu' pagine, per via di
    elementi di testo ruotato (loghi/intestazioni) che l'algoritmo di
    ricostruzione a griglia di pypdf non gestisce bene (segnalato anche nei
    log come "Rotated text discovered. Output will be incomplete."). 'plain'
    perde l'allineamento preciso delle colonne (non affidabile per
    columnGap), ma resta testo pulito e leggibile riga per riga, che e' cio'
    che serve perche' il resto della pipeline (regex multiriga, segno da
    parole chiave) funzioni."""
    reader = read_pdf(data)
    pages = [(page.extract_text() or '') for page in reader.pages]
    return '\n'.join(_strip_repeated_boilerplate(pages))


def read_pdf(data: bytes) -> PdfReader:
    """Apre un PDF tollerando un caso reale trovato in un file di un utente:
    dati spazzatura di un secondo PDF (incompleto) accodati subito dopo il
    primo %%EOF - probabile artefatto di un sistema di invio email/allegati.
    pypdf si blocca cercando lo startxref alla fine del file e trova quello
    del secondo PDF (inesistente/troncato). Se l'apertura normale fallisce,
    ritentiamo troncando ai primi byte fino al primo %%EOF, che di solito
    contengono un PDF completo e valido."""
    try:
        return PdfReader(BytesIO(data))
    except Exception:
        eof = data.find(b'%%EOF')
        if eof == -1:
            raise
        truncated = data[:eof + len(b'%%EOF')]
        return PdfReader(BytesIO(truncated))


def _build_recipe_prompt(sample: str, filename: str) -> str:
    return f"""Sei un esperto di estratti conto bancari italiani. Analizza questo CAMPIONE di testo
estratto da un PDF (puo' avere interruzioni di riga anomale dovute all'estrazione) e restituisci
una "ricetta" di estrazione: un'espressione regolare Python che, applicata con re.finditer() con i
flag re.MULTILINE (SENZA re.DOTALL: il punto "." NON attraversa gli a-capo) a TUTTO il testo (non
solo questo campione), individua ogni transazione.

File: {filename}

Campione (attenzione: gli spazi sono significativi, riflettono le colonne della tabella originale):
{sample}

Rispondi SOLO con un oggetto JSON valido (nessun testo extra, nessun blocco markdown):
{{"bankName": "nome banca se riconoscibile altrimenti null", "pattern": "regex Python con i gruppi nominati (?P<date>...), (?P<amount>...), (?P<description>...)", "dateFormat": "formato compatibile con strptime, es. %d/%m/%Y oppure %d/%m/%y", "amountSign": "explicit|negative|positive|columnGap", "signKeywords": {{"negative": ["parole che indicano un addebito/uscita"], "positive": ["parole che indicano un accredito/entrata"]}}, "columnGapThreshold": 10, "openingBalance": "saldo iniziale del periodo (numero, punto come separatore decimale, negativo se a debito) oppure null se non lo trovi nel campione", "closingBalance": "saldo finale del periodo (stessa convenzione) oppure null se non lo trovi"}}

Saldi per riconciliazione (openingBalance/closingBalance): quasi ogni estratto conto italiano dichiara da qualche parte nell'intestazione o nel riepilogo il saldo iniziale e il saldo finale del periodo (es. "Saldo iniziale", "Saldo al 01/01/2026", "Saldo precedente", "Nuovo saldo", "Saldo contabile finale"). Riportali come numeri se li trovi nel campione: servono per verificare in automatico, sommando le transazioni estratte, che la ricetta sia corretta. Se non compaiono nel campione lascia entrambi a null, senza inventarli.

Regole per il pattern:
- Un solo gruppo (?P<date>...), un solo (?P<amount>...), un solo (?P<description>...)
- Il gruppo amount deve contenere solo cifre, punti/virgole ed eventuale segno meno (niente simboli di valuta), MAI spazi iniziali: fai iniziare il gruppo esattamente dalla prima cifra, senza "\\s*" o "[ ]*" prima al suo interno (lo spazio prima dell'importo viene misurato automaticamente da chi applica la ricetta, per il caso 3 qui sotto)
- Causali multiriga (bonifici con beneficiario/IBAN/causale/TRN spesso vanno su 2-3 righe fisiche nel testo estratto): se noti nel campione che una transazione continua sulle righe successive (non inizia subito con una nuova data), fai catturare al gruppo description ANCHE quelle righe, cosi': `(?P<description>[\\s\\S]*?)(?=\\n[ \\t]*<stesso pattern data>\\s+<stesso pattern data secondo>|\\Z)` dove `<stesso pattern data>` e' lo stesso sotto-pattern (non nominato) usato per (?P<date>...) - cioe' la description continua finche' non trova l'inizio della PROSSIMA transazione (una riga che ricomincia con le date) o la fine del testo. IMPORTANTE: metti SEMPRE `[ \\t]*` subito dopo il `\\n` nel lookahead, prima del pattern della data, perche' il testo estratto allinea le colonne con spazi di riempimento e la riga successiva puo' avere spazi prima della data - senza quel `[ \\t]*` il lookahead non troverebbe MAI la transazione successiva e la description ingoierebbe tutto il resto del documento. NON usare re.DOTALL globale: usa `[\\s\\S]` che attraversa gli a-capo senza bisogno del flag, e resta cosi' delimitato dal lookahead invece di essere greedy su tutto il documento. Se invece nel campione ogni transazione sta sempre su una riga sola, va bene anche il semplice `(?P<description>[^\\n]+)`.

Come determinare il segno (importantissimo, ci sono TRE casi tipici, guarda con attenzione il campione prima di scegliere):

CASO 1 - segno esplicito nel testo (es. "-42,50" per le spese, "120,00" per le entrate): includi il segno nel gruppo amount, usa "amountSign": "explicit".

CASO 2 - un'unica colonna importo SEMPRE POSITIVA, ma la riga contiene una parola che indica la direzione (es. "Addebito", "Accredito", "Prelievo", "Versamento"): usa "amountSign": "negative" come default e valorizza "signKeywords" con le parole del CAMPIONE che distinguono spese da entrate.

CASO 3 - DUE COLONNE SEPARATE senza segno e senza parole di direzione (tipico di molte banche italiane: header tipo "USCITE ENTRATE" o "DARE AVERE" o "ADDEBITI ACCREDITI", e su ogni riga compare UN SOLO numero, o vicino alla data (colonna di sinistra, spesa) o spostato piu' a destra con piu' spazi prima (colonna di destra, entrata)): usa "amountSign": "columnGap". Conta nel campione, carattere per carattere, quanti spazi ci sono tipicamente subito prima di un importo in colonna sinistra (spesa) e quanti prima di uno in colonna destra (entrata), e imposta "columnGapThreshold" a un numero intermedio tra i due (chi applica la ricetta misura da solo lo spazio reale prima di ogni importo trovato e lo confronta con questa soglia: se >= soglia e' un'entrata positiva, altrimenti una spesa negativa). Non serve un gruppo dedicato per lo spazio, basta il numero di soglia.

Attenzione a un formato specifico (osservato su BNL/Hello Bank): dopo la doppia data (data operazione + data valuta) puo' comparire un piccolo NUMERO DI RIFERIMENTO/PROGRESSIVO dell'operazione (es. "11", "45", "48", "66" - poche cifre, SENZA virgola/punto decimale), che NON e' l'importo - l'importo vero in questo formato sta molto piu' avanti nella riga (spesso subito prima o dopo il simbolo "€", a volte addirittura DOPO la descrizione anziche' prima). Prima di scrivere il gruppo (?P<amount>...) subito dopo le date, verifica nel campione: il numero li' ha una virgola o un punto seguito da esattamente 2 cifre (es. "0,28" o "1.031,32")? Se e' un numero intero corto senza decimali, e' quasi certamente un codice, non l'importo - cerca il vero importo (con virgola/punto decimale, spesso vicino a "€") altrove nella riga e fai puntare li' il gruppo (?P<amount>...), anche se questo significa farlo comparire DOPO (?P<description>...) invece che prima (in tal caso il lookahead di fine-transazione va messo dopo il gruppo amount, non prima).

Altre regole:
- Non dare mai per scontato che un estratto abbia solo spese: controlla se compaiono bonifici in entrata, accrediti, stipendi, storni, vendite titoli
- Escludi dal pattern righe di saldo/intestazione/totali, includi tutte le transazioni vere
- Il pattern deve essere sintassi valida per il modulo `re` di Python"""


def _parse_amount(raw: str) -> Optional[float]:
    text = raw.strip().replace(' ', '').replace('€', '')
    if not text:
        return None
    # Notazione contabile con segno finale (es. "42,50-" per un addebito)
    trailing_negative = text.endswith('-')
    if trailing_negative:
        text = text[:-1]
    if re.match(r'^-?\d{1,3}(\.\d{3})*,\d+$', text):
        text = text.replace('.', '').replace(',', '.')
    elif re.match(r'^-?\d{1,3}(,\d{3})*\.\d+$', text):
        text = text.replace(',', '')
    else:
        text = text.replace(',', '.')
    try:
        value = float(text)
    except ValueError:
        return None
    return -abs(value) if trailing_negative else value


def _parse_date(raw: str, date_format: Optional[str]) -> Optional[str]:
    raw = raw.strip()
    if date_format:
        try:
            return datetime.strptime(raw, date_format).date().isoformat()
        except ValueError:
            pass
    try:
        return parse_date(raw, dayfirst=True).date().isoformat()
    except (ValueError, TypeError):
        return None


def _extract_iban(header_text: str) -> Optional[str]:
    """Cerca l'IBAN solo nell'intestazione (il campione mandato all'AI), non in
    tutto il testo: dentro le singole transazioni compaiono spesso IBAN di
    beneficiari di bonifici, che non sono il conto a cui appartiene l'estratto."""
    match = _IBAN_RE.search(header_text)
    if not match:
        return None
    candidate = re.sub(r'\s+', '', match.group(1)).upper()
    # _IBAN_RE tollera spazi tra i gruppi (vedi commento sulla regex) per
    # riconoscere un IBAN scritto staccato, ma questo rende la lunghezza
    # minima garantita dalla regex stessa piu' debole (un gruppo puo' essere
    # anche di 1 solo carattere). Un IBAN vero e proprio e' sempre lungo tra
    # 15 (i piu' corti, es. Norvegia) e 34 caratteri (il massimo IUPAC/ISO
    # 13616): scartiamo qui, in Python, un match troppo corto o troppo lungo
    # invece di provare a incastrare quel vincolo dentro la regex.
    return candidate if 15 <= len(candidate) <= 34 else None


def _extract_card_number(header_text: str) -> Optional[str]:
    match = _CARD_RE.search(header_text)
    return match.group(1) if match else None


# Parole italiane di causale bancaria non ambigue (addebito/accredito e affini):
# controllate SEMPRE per prime, indipendentemente da cosa l'AI ha dichiarato in
# "amountSign"/"signKeywords". Servono perche' l'AI ha sbagliato piu' volte a
# classificare il formato (es. Fineco dichiarato "explicit" quando in realta'
# non c'e' nessun "-" nel testo ma la riga contiene "Addebito"): queste parole
# sono affidabili a prescindere dalla modalita' scelta dalla ricetta, quindi
# fanno da rete di sicurezza sempre attiva invece di dipendere dal fatto che
# l'AI le abbia riconosciute correttamente.
_BUILTIN_NEGATIVE_KEYWORDS = [
    'addebito', 'prelievo', 'pagamento pos', 'canone', 'imposta di bollo',
    'commissione', 'sdd', 'rid', 'bonifico a favore di', 'a vs favore',
    'a vs. favore', 'acquisto',
    # "Vostro bonifico" (bug reale osservato su un estratto BNL/Hello Bank,
    # trovato tramite riconciliazione saldo) e' un bonifico DISPOSTO dal
    # cliente, quindi un'uscita - facilmente confuso con l'opposto "bonifico
    # A VOSTRO FAVORE" (quello si', un'entrata, gia' in _BUILTIN_POSITIVE_
    # KEYWORDS). L'ordine delle parole distingue i due casi, quindi le due
    # frasi non si sovrappongono mai per sbaglio.
    'vostro bonifico',
]
_BUILTIN_POSITIVE_KEYWORDS = [
    'accredito', 'versamento', 'bonifico a vostro favore', 'stipendio',
    'a vostro favore', 'rimborso', 'giroconto in entrata', 'vendita',
]


def _contains_keyword(text: str, keyword: str) -> bool:
    """Match a parola intera, non a sottostringa: altrimenti una parola
    chiave come "vendita" farebbe match anche dentro "Compravendita" (che in
    realta' e' ambiguo, puo' essere un acquisto o una vendita di titoli) -
    lo stesso tipo di bug gia' corretto per le parole chiave di
    categorizzazione ("tari" dentro "alimentari")."""
    return re.search(r'\b' + re.escape(keyword) + r'\b', text) is not None


# Intestazioni di colonna tipiche degli estratti a due colonne (spesa/entrata
# separate senza segno). Usate per trovare, sulla riga di intestazione della
# tabella, la posizione orizzontale reale delle due colonne: con
# extraction_mode='layout' quella posizione (carattere dall'inizio riga) e'
# sulla stessa griglia di tutta la pagina, quindi e' un riferimento diretto -
# molto piu' affidabile di una soglia dedotta statisticamente dagli spazi.
_COLUMN_HEADER_KEYWORDS = {
    'negative': ['uscite', 'addebiti', 'dare', 'prelievi'],
    'positive': ['entrate', 'accrediti', 'avere', 'versamenti'],
}


def _detect_column_header_offsets(full_text: str) -> Optional[Dict[str, int]]:
    """Cerca nel testo la riga di intestazione della tabella (es. "Data
    Uscite Entrate Descrizione") e restituisce la posizione orizzontale
    (carattere dall'inizio della riga) delle due colonne di importo. None se
    non trova una riga con entrambe le intestazioni riconoscibili."""
    for line in full_text.split('\n'):
        lower = line.lower()
        neg_pos = None
        pos_pos = None
        for kw in _COLUMN_HEADER_KEYWORDS['negative']:
            idx = lower.find(kw)
            if idx != -1 and (neg_pos is None or idx < neg_pos):
                neg_pos = idx
        for kw in _COLUMN_HEADER_KEYWORDS['positive']:
            idx = lower.find(kw)
            if idx != -1 and (pos_pos is None or idx < pos_pos):
                pos_pos = idx
        if neg_pos is not None and pos_pos is not None and neg_pos != pos_pos:
            return {'negative': neg_pos, 'positive': pos_pos}
    return None


def _column_offset(full_text: str, position: int) -> int:
    """Posizione orizzontale (carattere dall'inizio della propria riga) di
    una posizione nel testo - da confrontare con gli offset delle
    intestazioni di colonna trovati da _detect_column_header_offsets."""
    line_start = full_text.rfind('\n', 0, position) + 1
    return position - line_start


# I decimali sono OBBLIGATORI (non "(?:,\d{2})?"): senza, un numero di pagina
# come "1" (da "PAGINA 1 DI 5") verrebbe letto come importo valido e
# inquinerebbe gli indizi di colonna con valori 1.0-5.0 che possono collidere
# per valore con importi reali (es. "Imposta di Bollo" da 1,00 abbinato per
# sbaglio al numero di pagina invece che alla sua vera posizione in colonna) -
# bug reale trovato testando su un estratto conto vero.
_AMOUNT_TOKEN_RE = re.compile(r'^-?\d{1,3}(?:\.\d{3})*,\d{2}$')

_CURRENCY_SUFFIX_RE = re.compile(r'[\s€]+$')  # spazi e simbolo Euro finali


def _strip_currency(text: str) -> str:
    """Rimuove un simbolo Euro (o spazi) finale prima di riconoscere un
    importo: alcuni estratti (es. BNL/Hello Money) hanno il simbolo valuta
    attaccato al numero nello stesso frammento di testo ("319,18 €")."""
    return _CURRENCY_SUFFIX_RE.sub('', text)


def _combined_text_position(cm, tm) -> Tuple[float, float, float, float]:
    """Compone la matrice del testo (tm) con quella corrente (cm), come fa
    il motore PDF per posizionare davvero il testo sulla pagina. Restituisce
    (b, c, x, y): b/c sono le componenti di rotazione/inclinazione della
    matrice combinata (diverse da zero se il testo e' ruotato, es. loghi o
    watermark), x/y la posizione assoluta nella pagina."""
    b = tm[0] * cm[1] + tm[1] * cm[3]
    c = tm[2] * cm[0] + tm[3] * cm[2]
    x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
    y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
    return b, c, x, y


def _decode_pdf_string(value) -> str:
    """cp1252 (non latin-1) come ripiego: un font PDF con WinAnsiEncoding
    (comune) mappa il byte 0x80 al simbolo Euro "€" - con latin-1 quello
    stesso byte diventa un carattere di controllo invece del simbolo, e un
    importo come "319,18 €" non verrebbe piu' riconosciuto come importo
    valido (bug reale trovato su un estratto conto BNL/Hello Money)."""
    if isinstance(value, bytes):
        try:
            return value.decode('utf-8')
        except UnicodeDecodeError:
            try:
                return value.decode('cp1252')
            except UnicodeDecodeError:
                return value.decode('latin-1', errors='replace')
    return str(value)


def _collect_text_fragments(page) -> List[Tuple[float, float, str]]:
    """Frammenti di testo (y, x, testo) con la posizione REALE nella pagina,
    letti direttamente dagli operatori Tj/'/" del content stream (via
    visitor_operand_before), NON dall'API di alto livello visitor_text: su un
    estratto conto reale (Fineco) visitor_text FONDE in un'unica stringa (con
    la posizione del primo pezzo soltanto) quello che nel content stream sono
    invece Tj separati con posizioni X diverse per ogni campo (data, importo,
    descrizione, intestazioni di colonna) - perdendo esattamente
    l'informazione di colonna che ci serve. Leggendo gli operatori grezzi
    recuperiamo la posizione X vera di ognuno. Ignoriamo i frammenti
    ruotati/inclinati (es. loghi/watermark)."""
    fragments: List[Tuple[float, float, str]] = []

    def visitor(op, args, cm, tm):
        if op == b'Tj' and args:
            raw = args[0]
        elif op in (b"'", b'"') and args:
            raw = args[-1]
        else:
            return
        stripped = _decode_pdf_string(raw).strip()
        if not stripped:
            return
        rb, rc, x, y = _combined_text_position(cm, tm)
        if abs(rb) > 0.01 or abs(rc) > 0.01:
            return
        fragments.append((y, x, stripped))

    page.extract_text(visitor_operand_before=visitor)
    return fragments


def _group_fragments_into_rows(fragments: List[Tuple[float, float, str]], y_tolerance: float = 2.5) -> List[List[Tuple[float, str]]]:
    """Raggruppa i frammenti di testo nella stessa riga visiva (posizione Y
    simile, con tolleranza), ordinati dall'alto in basso e, dentro ogni riga,
    da sinistra a destra."""
    ordered = sorted(fragments, key=lambda f: (-f[0], f[1]))
    rows: List[List[Tuple[float, str]]] = []
    current: List[Tuple[float, str]] = []
    current_y = None
    for y, x, text in ordered:
        if current_y is not None and abs(y - current_y) > y_tolerance:
            rows.append(current)
            current = []
        current.append((x, text))
        current_y = y
    if current:
        rows.append(current)
    return rows


def _find_column_x_positions(rows: List[List[Tuple[float, str]]]) -> Optional[Dict[str, float]]:
    """Cerca la riga di intestazione della tabella (contiene sia una parola
    tipo 'uscite' che 'entrate') e restituisce la posizione X REALE delle due
    colonne di importo, letta dalle coordinate del PDF - non dedotta dagli
    spazi nel testo ricostruito."""
    for row in rows:
        neg_x = pos_x = None
        for x, text in row:
            low = text.lower()
            if neg_x is None and any(kw in low for kw in _COLUMN_HEADER_KEYWORDS['negative']):
                neg_x = x
            if pos_x is None and any(kw in low for kw in _COLUMN_HEADER_KEYWORDS['positive']):
                pos_x = x
        if neg_x is not None and pos_x is not None and neg_x != pos_x:
            return {'negative': neg_x, 'positive': pos_x}
    return None


def detect_column_sides_from_pdf(data: bytes) -> Optional[List[Tuple[float, str]]]:
    """Analizza il PDF pagina per pagina usando le coordinate reali del testo
    per determinare, per ogni importo trovato, in quale colonna si trova
    (Uscite/negative o Entrate/positive). Restituisce una lista (valore
    assoluto, lato) nello STESSO ORDINE del documento, da correlare poi con
    le transazioni estratte dalla ricetta regex (extract_transactions_with_
    recipe abbina ogni importo al primo valore corrispondente non ancora
    usato in questa lista). None se non trova mai un'intestazione di colonna
    riconoscibile (probabilmente non e' un formato a due colonne)."""
    try:
        reader = read_pdf(data)
    except Exception:
        return None
    column_x: Optional[Dict[str, float]] = None
    hints: List[Tuple[float, str]] = []
    for page in reader.pages:
        fragments = _collect_text_fragments(page)
        if not fragments:
            continue
        rows = _group_fragments_into_rows(fragments)
        page_columns = _find_column_x_positions(rows)
        if page_columns:
            column_x = page_columns
        if not column_x:
            continue
        for row in rows:
            for x, raw_text in row:
                text = _strip_currency(raw_text)
                if not _AMOUNT_TOKEN_RE.match(text):
                    continue
                value = _parse_amount(text)
                if value is None:
                    continue
                neg_dist = abs(x - column_x['negative'])
                pos_dist = abs(x - column_x['positive'])
                side = 'negative' if neg_dist <= pos_dist else 'positive'
                hints.append((abs(value), side))
    return hints or None


def _consume_column_hint(hints: List[Tuple[float, str]], consumed: List[bool], amount_value: float) -> Optional[str]:
    """Trova il primo indizio di colonna (da detect_column_sides_from_pdf)
    non ancora usato il cui valore corrisponde all'importo appena estratto
    dalla regex, e lo marca come usato. Il confronto e' per valore (non per
    posizione/ordine puro) perche' la regex puo' scartare righe che le
    coordinate intercettano (es. il saldo iniziale) - abbinare per valore e'
    piu' robusto che assumere lo stesso identico conteggio di righe."""
    target = abs(amount_value)
    for i, (value, side) in enumerate(hints):
        if not consumed[i] and abs(value - target) < 0.005:
            consumed[i] = True
            return side
    return None


def _resolve_sign(
    amount: float,
    description: str,
    sign_mode: str,
    sign_keywords: Dict[str, List[str]],
    gap_len: Optional[int],
    gap_threshold: Optional[float],
    column_side: Optional[str] = None,
    default_negative: bool = False,
) -> float:
    """Applica prima column_side (colonna reale Uscite/Entrate letta dalle
    coordinate del PDF, vedi detect_column_sides_from_pdf): e' un dato di
    fatto oggettivo del documento, piu' affidabile di qualunque parola chiave
    o classificazione amountSign dell'AI (una parola come "vendita" puo'
    comparire in causali ambigue, es. "Compravendita Titoli" che puo' essere
    un acquisto O una vendita - la colonna reale non mente). Solo se
    column_side non e' disponibile (formati a colonna singola come ING/Conto
    Arancio, senza Uscite/Entrate separate) si ripiega sulle parole chiave
    built-in, poi su quelle dichiarate dall'AI, poi su columnGap/gap_threshold
    (euristica sugli spazi, meno affidabile), poi sul default amountSign.
    Se nessuno di questi determina il segno e default_negative e' True (un
    rendiconto di carta di credito, dove ogni riga senza altra indicazione e'
    per definizione un acquisto/spesa - vedi ai_extract_transactions_from_pdf),
    il segno finale e' negativo invece di restare quello grezzo estratto dal
    testo."""
    if column_side == 'negative':
        return -abs(amount)
    if column_side == 'positive':
        return abs(amount)
    text = description.lower()
    for kw in _BUILTIN_NEGATIVE_KEYWORDS:
        if _contains_keyword(text, kw):
            return -abs(amount)
    for kw in _BUILTIN_POSITIVE_KEYWORDS:
        if _contains_keyword(text, kw):
            return abs(amount)
    for kw in sign_keywords.get('negative') or []:
        if kw and _contains_keyword(text, kw.lower()):
            return -abs(amount)
    for kw in sign_keywords.get('positive') or []:
        if kw and _contains_keyword(text, kw.lower()):
            return abs(amount)
    if sign_mode == 'columnGap' and gap_len is not None and gap_threshold is not None:
        return abs(amount) if gap_len >= gap_threshold else -abs(amount)
    if sign_mode == 'negative':
        return -abs(amount)
    if sign_mode == 'positive':
        return abs(amount)
    if default_negative:
        return -abs(amount)
    return amount


def _has_uncaptured_minus_before(full_text: str, start: int) -> bool:
    """Vero se subito prima dell'inizio del gruppo amount (saltando eventuali
    spazi) c'e' un "-" che il regex generato dall'AI non ha incluso nel gruppo
    (errore plausibile: il gruppo amount cattura solo cifre, dimenticando un
    "-?" iniziale). Senza questo controllo un segno esplicito nel testo
    andrebbe perso silenziosamente, con importi risultanti tutti positivi."""
    i = start - 1
    while i >= 0 and full_text[i] in ' \t':
        i -= 1
    return i >= 0 and full_text[i] == '-'


def _count_leading_space(full_text: str, amount_start: int) -> int:
    """Conta gli spazi/tab immediatamente prima della posizione REALE del
    match (non del gruppo dedicato): un \\s+ greedy altrove nel pattern puo'
    "mangiarsi" gli spazi prima che un eventuale gruppo (?P<gap>...) li veda,
    ma la posizione del match nel testo resta corretta in ogni caso, quindi
    contiamo da li' invece di fidarci di un gruppo scritto dall'AI."""
    i = amount_start - 1
    count = 0
    while i >= 0 and full_text[i] in ' \t':
        count += 1
        i -= 1
    return count


def _ensure_lookahead_is_last(pattern: str) -> str:
    """Bug strutturale reale osservato (rendiconto carta di credito ING,
    dove l'importo sta DOPO la descrizione invece che prima): l'AI a volte
    scrive il lookahead di fine-description PRIMA del gruppo (?P<amount>...)
    invece che dopo, es. "...(?P<description>...)(?=\\n<data>|\\Z)[ \\t]*
    (?P<amount>...)". Il lookahead e' un'asserzione a LARGHEZZA ZERO (non
    consuma testo): tutto cio' che viene scritto dopo di lui deve comunque
    trovare testo vero da quella stessa posizione, ma se li' il documento
    prosegue con la RIGA SUCCESSIVA (o e' proprio la fine del testo, \\Z), il
    gruppo (?P<amount>...) scritto dopo non trova mai nulla da catturare - il
    pattern non puo' fare match da nessuna parte. Se c'e' del testo dopo la
    chiusura del lookahead, lo spostiamo PRIMA di esso (il lookahead deve
    essere l'ultima cosa: verifica cosa viene dopo, non lo consuma)."""
    date_span = _find_group_span(pattern, '(?P<date>')
    if date_span is None:
        return pattern
    _, _, date_group_end = date_span
    lookahead_start = pattern.find('(?=', date_group_end)
    if lookahead_start == -1:
        return pattern
    lookahead_span = _find_group_span(pattern, '(?=', lookahead_start)
    if lookahead_span is None:
        return pattern
    _, _, lookahead_group_end = lookahead_span
    trailing = pattern[lookahead_group_end:]
    if not trailing:
        return pattern
    lookahead_text = pattern[lookahead_start:lookahead_group_end]
    # In questa struttura (importo alla fine della riga) l'importo e' sempre
    # l'ultima cosa sulla propria riga fisica: aggiungiamo "fine riga" come
    # ulteriore condizione valida per il confine, oltre a quelle scritte
    # dall'AI (prossima transazione / \Z) - un documento reale puo' finire
    # con testo legale o un numero di pagina invece che con un numero, per
    # cui \Z da solo non e' mai raggiungibile subito dopo l'ultimo importo.
    lookahead_text = lookahead_text[:-1] + '|' + chr(92) + 'n)'
    return pattern[:lookahead_start] + trailing + lookahead_text


def _ensure_lookahead_tolerates_leading_space(pattern: str) -> str:
    """Il testo estratto in extraction_mode='layout' allinea le colonne con
    spazi di riempimento: la riga della transazione successiva puo' avere
    spazi prima della data. Se il lookahead di fine-description scritto
    dall'AI e' "(?=\\n<data>...)" senza tollerare quegli spazi, non trova mai
    la transazione successiva e la description ingoia tutto il resto del
    documento (un'unica transazione estratta). Anziche' fidarsi che l'AI
    segua l'istruzione del prompt, lo garantiamo qui in modo deterministico:
    inserire "[ \\t]*" dopo un "\\n" a inizio lookahead e' sempre sicuro
    (corrisponde anche a zero spazi, quindi non cambia nulla se non serviva)."""
    backslash = chr(92)
    token = '(?=' + backslash + 'n'
    replacement = '(?=' + backslash + 'n[ ' + backslash + 't]*'
    return pattern.replace(token, replacement)


def _ensure_date_group_has_boundary(pattern: str) -> str:
    """Bug reale osservato (log di produzione): un estratto contiene spesso
    altrove nel testo una data con anno a 4 cifre (es. intestazione "Data
    Documento 31.03.2026"). Se la ricetta usa un pattern data con anno a 2
    cifre (dd.mm.yy), quella data a 4 cifre soddisfa comunque il pattern
    prendendone solo i primi 6 caratteri ("31.03.20"), agganciando un match
    falso positivo molto prima della prima vera transazione (e mandando in
    tilt tutta l'estrazione). Aggiungiamo "(?!\\d)" subito dopo il gruppo
    (?P<date>...) cosi' il match fallisce se seguito da un'altra cifra."""
    marker = '(?P<date>'
    start = pattern.find(marker)
    if start == -1:
        return pattern
    i = start + len(marker)
    depth = 1
    while i < len(pattern) and depth > 0:
        ch = pattern[i]
        if ch == chr(92):  # backslash: il carattere dopo e' sempre letterale, non contare parentesi
            i += 2
            continue
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        i += 1
    if depth != 0:
        return pattern
    guard = '(?!' + chr(92) + 'd)'
    return pattern[:i] + guard + pattern[i:]


def _ensure_second_date_column_skipped(pattern: str) -> str:
    """Bug reale osservato due volte (Fineco e Conto Arancio/ING): molti
    estratti hanno DUE date per riga (data operazione + data valuta) prima
    dell'importo, ma la ricetta a volte prevede solo la prima e fa seguire
    subito il gruppo (?P<amount>...). In quel caso l'importo cattura solo i
    primi 2 caratteri della seconda data (es. "17" da "17/03/2026 126,80"),
    sballando importo e descrizione. Inseriamo un salto opzionale di
    un'eventuale seconda data subito prima di (?P<amount>...): se la seconda
    data non c'e' (formati a data singola) il gruppo e' opzionale e non
    cambia nulla, se c'e' viene consumata cosi' l'importo resta quello vero.
    Il gruppo e' nominato (?P<value_date>...) invece di non-capturing: quando
    presente e' la vera data valuta della transazione, salvata a parte per
    migliorare il riconoscimento dei doppioni (vedi _finalize_import)."""
    marker = '(?P<amount>'
    idx = pattern.find(marker)
    if idx == -1:
        return pattern
    skip = r'(?:\s*(?P<value_date>\d{1,4}[-./]\d{1,2}[-./]\d{1,4})\s*)?'
    return pattern[:idx] + skip + pattern[idx:]


def _find_group_span(pattern: str, marker: str, search_from: int = 0):
    """Trova l'indice di inizio/fine del contenuto di un gruppo con nome
    (es. "(?P<date>"), gestendo le parentesi annidate e gli escape. Ritorna
    (content_start, content_end, group_end) o None se non trovato/non
    bilanciato. group_end e' l'indice subito dopo la ")" di chiusura."""
    start = pattern.find(marker, search_from)
    if start == -1:
        return None
    i = start + len(marker)
    depth = 1
    while i < len(pattern) and depth > 0:
        ch = pattern[i]
        if ch == chr(92):
            i += 2
            continue
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        i += 1
    if depth != 0:
        return None
    return start + len(marker), i - 1, i


def _simplify_lookahead_to_date_boundary(pattern: str) -> str:
    """Il lookahead che delimita la fine della description spesso verifica
    anche la "forma" dell'importo della transazione successiva, non solo che
    inizi con una data - ma l'AI scrive quel controllo in modo diverso ogni
    volta (a volte manca il separatore delle migliaia, a volte manca il
    punto nella classe di caratteri, a volte un quantificatore troppo
    stretto): rincorrere ogni variante con un replace testuale e' fragile e
    si e' rotto piu' volte (bug reali osservati su estratti ING/Conto
    Arancio diversi). Dato che su tutti gli estratti reali visti finora una
    transazione inizia SEMPRE con una data (eventualmente doppia), il
    lookahead viene ricostruito per verificare SOLO quello, scartando
    qualunque controllo sull'importo scritto dall'AI - piu' semplice e piu'
    robusto perche' non dipende da come l'AI ha scritto quella parte."""
    date_span = _find_group_span(pattern, '(?P<date>')
    if date_span is None:
        return pattern
    date_start, date_end, date_group_end = date_span
    date_subpattern = pattern[date_start:date_end]
    if not date_subpattern:
        return pattern

    lookahead_start = pattern.find('(?=', date_group_end)
    if lookahead_start == -1:
        return pattern
    lookahead_span = _find_group_span(pattern, '(?=', lookahead_start)
    if lookahead_span is None:
        return pattern
    la_content_start, la_content_end, la_group_end = lookahead_span
    lookahead_content = pattern[la_content_start:la_content_end]

    idx = lookahead_content.find(date_subpattern)
    if idx == -1:
        return pattern
    prefix = lookahead_content[:idx]  # tipicamente qualcosa come "\n[ \t]*"
    has_end_anchor = chr(92) + 'Z' in lookahead_content
    # "fine riga" aggiunta da _ensure_lookahead_is_last per le strutture con
    # importo alla fine della riga (vedi quella funzione) - va preservata,
    # altrimenti questa ricostruzione la butterebbe via.
    has_newline_alt = '|' + chr(92) + 'n' in lookahead_content
    skip = r'(?:\s*\d{1,4}[-./]\d{1,2}[-./]\d{1,4}\s*)?'
    new_content = prefix + date_subpattern + skip
    if has_end_anchor:
        new_content += '|' + chr(92) + 'Z'
    if has_newline_alt:
        new_content += '|' + chr(92) + 'n'
    return pattern[:la_content_start] + new_content + pattern[la_content_end:]


def _ensure_amount_group_supports_thousands(pattern: str) -> str:
    """Sostituisce SEMPRE il contenuto di (?P<amount>...) con il pattern
    canonico (con separatore delle migliaia). Non basta "rileggere" l'importo
    dopo il match (fatto in extract_transactions_with_recipe): se il gruppo
    originale e' troppo permissivo (es. "-?\\d{1,3}(?:[.,]\\d{2})?", soddisfatto
    anche da 1 sola cifra), quando il match con l'anno completo di una
    seconda data fallisce (per via del salto opzionale aggiunto da
    _ensure_second_date_column_skipped) il motore regex fa backtracking e
    trova un'altra combinazione "valida" ma sbagliata (es. anno letto come
    "202" invece di "2026", lasciando "6" come importo) - un bug reale
    osservato su un estratto ING/Conto Arancio. Sostituendo il gruppo con un
    pattern che richiede l'intera cifra dell'importo, quella scorciatoia
    sbagliata non e' piu' disponibile al motore regex."""
    marker = '(?P<amount>'
    start = pattern.find(marker)
    if start == -1:
        return pattern
    i = start + len(marker)
    depth = 1
    while i < len(pattern) and depth > 0:
        ch = pattern[i]
        if ch == chr(92):
            i += 2
            continue
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        i += 1
    if depth != 0:
        return pattern
    return pattern[:start + len(marker)] + _CANONICAL_AMOUNT_RE.pattern + pattern[i - 1:]


def _auto_column_gap_threshold(gap_lens: List[int]) -> Optional[float]:
    """Calcola la soglia separando le due colonne (spesa/entrata) dai dati
    REALI di tutto l'estratto, invece di usare il numero indovinato dall'AI
    guardando un campione piccolo (che si e' dimostrato inaffidabile, es. su
    Fineco): ordina le lunghezze di spazio osservate prima di ogni importo e
    trova il punto in cui il salto tra due valori consecutivi e' piu' grande
    (metodo del "gap massimo", clustering 1D a due gruppi) - separa la
    colonna di sinistra da quella di destra molto meglio di una soglia
    fissa stimata su poche righe di esempio."""
    distinct = sorted(set(gap_lens))
    if len(distinct) < 2:
        return None
    best_jump = -1
    best_threshold = None
    for i in range(1, len(distinct)):
        jump = distinct[i] - distinct[i - 1]
        if jump > best_jump:
            best_jump = jump
            best_threshold = (distinct[i] + distinct[i - 1]) / 2
    return best_threshold


def _find_card_settlement_row(full_text: str) -> Optional[Dict[str, Any]]:
    """Cerca _CARD_SETTLEMENT_LINE_RE in tutto il testo, indipendentemente da
    cosa la ricetta AI ha o non ha catturato (vedi commento sulla regex)."""
    match = _CARD_SETTLEMENT_LINE_RE.search(full_text)
    if not match:
        return None
    date_iso = _parse_date(match.group('valuta') or match.group('opdate'), None)
    amount = _parse_amount(match.group('amount'))
    if date_iso is None or amount is None:
        return None
    value_date_iso = _parse_date(match.group('valuta'), None) if match.group('valuta') else None
    return {
        'date': date_iso,
        'value_date': value_date_iso if value_date_iso != date_iso else None,
        'amount': abs(amount),
        'description': 'Addebito in C/C (pagamento saldo carta di credito)',
        'isCardSettlement': True,
    }


def extract_transactions_with_recipe(
    full_text: str,
    recipe: Dict[str, Any],
    column_hints: Optional[List[Tuple[float, str]]] = None,
    default_negative: bool = False,
) -> List[Dict[str, Any]]:
    """Applica la ricetta generata dall'AI (regex + formato data + segno) a
    tutto il testo dell'estratto, in locale: l'AI non deve piu' ricopiare ogni
    transazione (costoso e soggetto a troncamento sugli estratti lunghi).
    column_hints (da detect_column_sides_from_pdf, coordinate reali nel PDF)
    ha priorita' sul segno dichiarato dalla ricetta quando disponibile,
    perche' l'AI ha dimostrato di scegliere "explicit" anche su estratti che
    sono in realta' a due colonne senza segno ne' parole di direzione."""
    pattern = recipe.get('pattern')
    if not pattern:
        raise ValueError("La ricetta di estrazione generata dall'AI non contiene un pattern")
    pattern = _ensure_lookahead_is_last(pattern)
    pattern = _ensure_lookahead_tolerates_leading_space(pattern)
    pattern = _ensure_date_group_has_boundary(pattern)
    pattern = _ensure_second_date_column_skipped(pattern)
    pattern = _simplify_lookahead_to_date_boundary(pattern)
    pattern = _ensure_amount_group_supports_thousands(pattern)
    try:
        compiled = re.compile(pattern, re.MULTILINE)
    except re.error as e:
        raise ValueError(f"Il pattern generato dall'AI non e' un'espressione regolare valida: {e}")
    if 'amount' not in compiled.groupindex:
        raise ValueError("Il pattern generato dall'AI non contiene il gruppo (?P<amount>...)")

    date_format = recipe.get('dateFormat')
    sign_mode = recipe.get('amountSign') or 'explicit'
    sign_keywords = recipe.get('signKeywords') or {}
    header_offsets = _detect_column_header_offsets(full_text) if sign_mode == 'columnGap' else None
    if header_offsets:
        print(f'[pdf_import] intestazioni di colonna trovate nel testo: {header_offsets}', flush=True)
    if column_hints:
        print(f'[pdf_import] {len(column_hints)} indizi di colonna dalle coordinate reali del PDF', flush=True)
    hints_consumed = [False] * len(column_hints) if column_hints else None

    # Prima passata: estrae i campi grezzi e (se serve) la lunghezza dello
    # spazio prima di ogni importo, senza ancora risolvere il segno - serve
    # per calcolare la soglia columnGap sui dati reali di TUTTO l'estratto
    # invece che sulla stima dell'AI.
    raw_rows = []
    gap_lens = []
    for m in compiled.finditer(full_text):
        groups = m.groupdict()
        date_iso = _parse_date(groups.get('date') or '', date_format)
        value_date_iso = _parse_date(groups.get('value_date') or '', date_format) if groups.get('value_date') else None
        amount_text = groups.get('amount') or ''
        canonical_match = _CANONICAL_AMOUNT_RE.match(full_text, pos=m.start('amount'))
        if canonical_match and len(canonical_match.group(0)) > len(amount_text):
            amount_text = canonical_match.group(0)
        amount = _parse_amount(amount_text)
        description = re.sub(r'\s+', ' ', (groups.get('description') or '')).strip()[:400] or 'Importazione'
        if date_iso is None or amount is None:
            continue
        if _BALANCE_SNAPSHOT_RE.match(description):
            continue
        if amount > 0 and not amount_text.strip().startswith('-') and _has_uncaptured_minus_before(full_text, m.start('amount')):
            amount = -amount
        column_side = None
        if column_hints:
            column_side = _consume_column_hint(column_hints, hints_consumed, amount)
        gap_len = None
        if sign_mode == 'columnGap':
            gap_len = _count_leading_space(full_text, m.start('amount'))
            gap_lens.append(gap_len)
            if column_side is None and header_offsets:
                offset = _column_offset(full_text, m.start('amount'))
                neg_dist = abs(offset - header_offsets['negative'])
                pos_dist = abs(offset - header_offsets['positive'])
                column_side = 'negative' if neg_dist <= pos_dist else 'positive'
        raw_rows.append({
            'date': date_iso, 'value_date': value_date_iso, 'amount': amount, 'description': description,
            'gap_len': gap_len, 'column_side': column_side,
        })

    gap_threshold = _auto_column_gap_threshold(gap_lens) if sign_mode == 'columnGap' else None
    if gap_threshold is None:
        gap_threshold = recipe.get('columnGapThreshold')

    rows = []
    for r in raw_rows:
        # default_negative arriva da is_credit_card_statement (vedi
        # ai_extract_transactions_from_pdf): il testo "addebito in c/c" ha
        # questo significato speciale (pagamento del saldo, non una spesa)
        # SOLO su un rendiconto carta di credito. Sul conto corrente la
        # stessa frase (se mai comparisse) descriverebbe un'uscita vera, e va
        # trattata come tutte le altre righe - senza questo controllo un
        # conto corrente che citasse "addebito in c/c" per un'altra causale
        # perderebbe quell'uscita facendola diventare positiva per sbaglio.
        if default_negative and _CARD_SETTLEMENT_RE.match(r['description']):
            # Non e' una spesa ne' un'entrata reale, e' il pagamento del saldo
            # carta ricevuto dal conto corrente: sul rendiconto carta va
            # SEMPRE positivo (riduce il debito), a prescindere da
            # segno/parola chiave/colonna della ricetta - la parola
            # "addebito" qui indicherebbe altrimenti una spesa (vedi
            # _BUILTIN_NEGATIVE_KEYWORDS), che e' il segno sbagliato per
            # questa riga. Va importata (non scartata) e marcata come
            # trasferimento: vedi is_card_settlement in _finalize_import.
            row = {
                'date': r['date'], 'value_date': r['value_date'], 'amount': abs(r['amount']),
                'description': r['description'], 'isCardSettlement': True,
            }
        else:
            amount = _resolve_sign(
                r['amount'], r['description'], sign_mode, sign_keywords,
                r['gap_len'], gap_threshold, r['column_side'], default_negative,
            )
            row = {'date': r['date'], 'value_date': r['value_date'], 'amount': amount, 'description': r['description']}
        rows.append(row)

    if default_negative and not any(r.get('isCardSettlement') for r in rows):
        settlement_row = _find_card_settlement_row(full_text)
        if settlement_row:
            print(
                f"[pdf_import] riga di pagamento saldo carta trovata direttamente nel testo (la ricetta non "
                f"l'ha intercettata, struttura diversa dalle altre righe): {settlement_row['description']!r} "
                f"{settlement_row['amount']}",
                flush=True,
            )
            rows.append(settlement_row)

    return rows


def _check_same_sign(rows: List[Dict[str, Any]]) -> Optional[str]:
    """Se TUTTE le transazioni di un estratto risultano dello stesso segno, e'
    un sintomo tipico di un rilevamento del segno sbagliato (amountSign/
    signKeywords non hanno distinto spese da entrate): non blocca l'import
    (potrebbe anche essere un estratto di sole spese/entrate reali), ma
    restituisce un avviso da mostrare all'utente prima che confermi tutto."""
    if len(rows) < 3:
        return None
    if all(r['amount'] >= 0 for r in rows) or all(r['amount'] <= 0 for r in rows):
        return (
            f'Attenzione: tutte le {len(rows)} transazioni estratte hanno lo stesso segno. Se questo estratto '
            "contiene sia spese che entrate, il segno potrebbe non essere stato riconosciuto correttamente: "
            'controlla prima di confermarle.'
        )
    return None


def _reconcile(rows: List[Dict[str, Any]], recipe: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Verifica la ricetta contro un dato oggettivo del documento (non contro
    se stessa): la somma delle transazioni estratte deve corrispondere alla
    differenza saldo finale - saldo iniziale dichiarata dalla banca
    (openingBalance/closingBalance, vedi _build_recipe_prompt). Restituisce
    ('ok'|'mismatch'|'unknown', messaggio). 'unknown' se il campione non
    conteneva questi saldi (l'AI non puo' inventarli) - in quel caso non c'e'
    modo di verificare automaticamente, quindi non e' ne' un successo ne' un
    fallimento. Tolleranza ampia (2%, minimo 1 euro) perche' il saldo
    dichiarato puo' includere competenze/interessi non ancora contabilizzati
    come transazioni singole - qui cerchiamo un errore grossolano di ricetta
    (importi/segni sbagliati), non un arrotondamento."""
    opening, closing = recipe.get('openingBalance'), recipe.get('closingBalance')
    if opening is None or closing is None:
        return 'unknown', None
    try:
        opening, closing = float(opening), float(closing)
    except (TypeError, ValueError):
        return 'unknown', None
    computed = sum(r['amount'] for r in rows)
    expected = closing - opening
    tolerance = max(1.0, abs(expected) * 0.02)
    if abs(computed - expected) <= tolerance:
        return 'ok', None
    message = (
        f'Le transazioni estratte sommano a {computed:.2f} €, ma la differenza tra saldo finale '
        f"({closing:.2f} €) e saldo iniziale ({opening:.2f} €) dichiarata nell'estratto e' {expected:.2f} €: "
        'la ricetta di estrazione potrebbe avere importi o segni sbagliati.'
    )
    return 'mismatch', message


def _get_cached_recipe(cache_key: str) -> Optional[Dict[str, Any]]:
    row = db.conn.execute(
        'SELECT recipe_json FROM pdf_import_recipes WHERE cache_key = ?', (cache_key,)
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row['recipe_json'])
    except (json.JSONDecodeError, TypeError):
        return None


def _save_recipe(cache_key: str, bank_name: Optional[str], recipe: Dict[str, Any]) -> None:
    """Salva/aggiorna la ricetta SOLO quando _reconcile l'ha appena confermata
    'ok' (vedi ai_extract_transactions_from_pdf): mai un salvataggio
    ottimistico, altrimenti una ricetta sbagliata ma indistinguibile a
    occhio resterebbe in cache e sbaglierebbe ogni import successivo dello
    stesso conto invece di essere ricontrollata."""
    db.conn.execute(
        '''INSERT INTO pdf_import_recipes (cache_key, bank_name, recipe_json, last_validated_at, updated_at)
           VALUES (?, ?, ?, datetime('now'), datetime('now'))
           ON CONFLICT(cache_key) DO UPDATE SET
             bank_name = excluded.bank_name,
             recipe_json = excluded.recipe_json,
             last_validated_at = datetime('now'),
             updated_at = datetime('now')''',
        (cache_key, bank_name, json.dumps(recipe, ensure_ascii=False)),
    )
    db.conn.commit()


def _build_recipe_retry_prompt(sample: str, filename: str, previous_recipe: Dict[str, Any], feedback: str) -> str:
    return _build_recipe_prompt(sample, filename) + f"""

Hai gia' tentato con questa ricetta:
{json.dumps(previous_recipe, ensure_ascii=False)}

Ma il risultato non e' corretto: {feedback}

Correggi la ricetta (pattern, amountSign/signKeywords, o i saldi) e restituisci di nuovo SOLO l'oggetto JSON, nello stesso formato."""


def _warn_if_looks_incomplete(full_text: str, extracted_count: int) -> None:
    """Confronto grezzo (solo un log, non blocca l'import): se nel testo ci
    sono molte piu' date di quante transazioni estratte, il pattern generato
    dall'AI potrebbe non coprire tutto il formato dell'estratto. Le date
    possono comparire piu' volte per transazione (es. 'data operazione' nelle
    causali carta), quindi non e' un segnale affidabile per bloccare l'import,
    solo per un avviso nei log dell'addon."""
    date_tokens = len(set(_DATE_TOKEN_RE.findall(full_text)))
    if date_tokens and extracted_count < date_tokens * 0.3:
        print(
            f'[pdf_import] attenzione: estratte solo {extracted_count} transazioni a fronte di {date_tokens} '
            'date distinte trovate nel testo - il pattern potrebbe non coprire tutto il formato dell\'estratto.',
            flush=True,
        )


def _log_sample_match(recipe: Dict[str, Any], header: str) -> None:
    """Logga il primo match del pattern nel campione (gruppi grezzi, prima di
    qualunque parsing/segno): utile per capire perche' il segno di un estratto
    e' risultato sbagliato senza dover riprodurre il problema con il file
    originale, che l'addon non conserva dopo l'estrazione del testo."""
    pattern = recipe.get('pattern')
    if not pattern:
        return
    try:
        match = re.search(pattern, header, re.MULTILINE)
    except re.error as e:
        print(f'[pdf_import] pattern non valido, impossibile fare un match di prova: {e}', flush=True)
        return
    if match:
        print(f'[pdf_import] primo match nel campione (gruppi grezzi): {match.groupdict()}', flush=True)
    else:
        print("[pdf_import] il pattern non ha trovato nessun match nel campione mandato all'AI", flush=True)


def _build_direct_extraction_prompt(filename: str) -> str:
    return f"""Sei un esperto di estratti conto bancari italiani. Nel PDF allegato ({filename}) individua OGNI
transazione (bonifici, addebiti, accrediti, pagamenti con carta, bollettini, commissioni, ecc.), leggendo con
attenzione il layout reale delle colonne del documento: a volte l'importo vero compare distante dalla data
(non subito dopo), oppure va distinto da un numero di riferimento/progressivo dell'operazione (poche cifre,
senza virgola/punto decimale) che NON e' l'importo.

Rispondi SOLO con un oggetto JSON valido (nessun testo extra, nessun blocco markdown), in questo formato:
{{"bankName": "nome banca se riconoscibile altrimenti null", "openingBalance": saldo iniziale del periodo (numero, negativo se a debito, o null se non lo trovi), "closingBalance": saldo finale del periodo (stessa convenzione, o null), "transactions": [{{"date": "AAAA-MM-GG", "amount": numero (negativo per spese/addebiti/uscite, positivo per entrate/accrediti), "description": "causale"}}]}}

Regole:
- NON includere righe di saldo iniziale/finale/periodo come transazioni, solo movimenti veri
- Segno: negativo per uscite/addebiti/spese/prelievi/pagamenti, positivo per entrate/accrediti/bonifici ricevuti/stipendi
- Se il documento ha piu' pagine, elenca le transazioni di TUTTE le pagine, non solo la prima
- Non inventare transazioni che non vedi nel documento, e non arrotondare gli importi"""


def _normalize_direct_row(row: Dict[str, Any], is_credit_card_statement: bool) -> Optional[Dict[str, Any]]:
    """Normalizza una riga restituita dall'estrazione diretta (l'AI puo'
    restituire l'importo sia come numero che come stringa con virgola, e la
    data non sempre nel formato AAAA-MM-GG richiesto nel prompt).
    is_credit_card_statement (vedi ai_extract_transactions_from_pdf) delimita
    dove "addebito in c/c" significa il pagamento del saldo carta invece di
    un'uscita qualunque - stessa cautela di extract_transactions_with_recipe."""
    if not isinstance(row, dict):
        return None
    description = re.sub(r'\s+', ' ', str(row.get('description') or '')).strip()[:400] or 'Importazione'
    if _BALANCE_SNAPSHOT_RE.match(description):
        return None
    date_raw = row.get('date')
    date_iso = None
    if isinstance(date_raw, str) and date_raw.strip():
        try:
            date_iso = datetime.strptime(date_raw.strip(), '%Y-%m-%d').date().isoformat()
        except ValueError:
            date_iso = _parse_date(date_raw, None)
    if date_iso is None:
        return None
    amount_raw = row.get('amount')
    amount = amount_raw if isinstance(amount_raw, (int, float)) else _parse_amount(str(amount_raw or ''))
    if amount is None:
        return None
    result = {'date': date_iso, 'amount': float(amount), 'description': description}
    if is_credit_card_statement and _CARD_SETTLEMENT_RE.match(description):
        result['isCardSettlement'] = True
    return result


def _ai_extract_transactions_direct_from_pdf(
    pdf_bytes: bytes, filename: str, is_credit_card_statement: bool, text: str
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str, Optional[str]]:
    """Fallback finale quando l'estrazione via ricetta regex fallisce (nessuna
    transazione trovata, o riconciliazione saldo fallita, per
    _MAX_RECIPE_ATTEMPTS tentativi consecutivi): manda il PDF originale (non
    solo un campione di testo appiattito) all'AI e le chiede di leggere
    direttamente le transazioni, sfruttando la sua capacita' di vedere il
    layout reale del documento invece di applicare una regex generata a
    priori su testo che ha gia' perso l'informazione di colonna/posizione.
    Piu' costoso (tutto il documento, non un campione) quindi usato solo
    come ultima risorsa, non al posto della ricetta regex."""
    prompt = _build_direct_extraction_prompt(filename)
    content = ai_client.ask_ai_with_pdf(prompt, pdf_bytes, filename, max_tokens=8000)
    parsed = ai_client.parse_json_object(content)
    raw_transactions = parsed.get('transactions') or []
    rows = []
    dropped = []
    for raw_row in raw_transactions:
        normalized = _normalize_direct_row(raw_row, is_credit_card_statement)
        if normalized:
            if normalized.get('isCardSettlement'):
                # Pagamento del saldo carta dal conto corrente: sempre positivo
                # (vedi lo stesso caso in extract_transactions_with_recipe),
                # a prescindere da come l'AI ha giudicato il segno da sola.
                normalized['amount'] = abs(normalized['amount'])
            else:
                # Rete di sicurezza sul segno anche qui: qui non c'e' una ricetta con
                # sign_mode/gap da applicare, ma le parole chiave built-in (vedi
                # _resolve_sign) restano affidabili a prescindere da come l'AI ha
                # giudicato il segno da sola - bug reale osservato (estratto BNL):
                # "Vostro bonifico" (un bonifico disposto dal cliente, un'uscita)
                # letto come entrata perche' contiene la parola "bonifico".
                normalized['amount'] = _resolve_sign(
                    normalized['amount'], normalized['description'], 'explicit', {}, None, None, None, False,
                )
            rows.append(normalized)
        else:
            dropped.append(raw_row)
    # Logghiamo sempre il dettaglio (non solo il conteggio): se la riconciliazione
    # fallisce anche qui, e' l'unico modo per capire senza rifare la chiamata se
    # l'AI ha davvero saltato transazioni, ha sbagliato importi/segni, oppure se
    # e' _normalize_direct_row a scartare righe valide per un formato inatteso di
    # data/importo restituito dall'AI (bug reale gia' visto sul percorso regex:
    # capire il "perche'" richiede vedere i dati, non solo il totale).
    print(
        f"[pdf_import] estrazione diretta dal PDF: {len(raw_transactions)} transazioni restituite dall'AI, "
        f'{len(rows)} normalizzate correttamente, {len(dropped)} scartate',
        flush=True,
    )
    if dropped:
        print(f'[pdf_import] righe scartate (data/importo non riconosciuto): {dropped[:15]}', flush=True)
    if is_credit_card_statement and not any(r.get('isCardSettlement') for r in rows):
        settlement_row = _find_card_settlement_row(text)
        if settlement_row:
            print(
                f"[pdf_import] riga di pagamento saldo carta trovata direttamente nel testo (l'AI non l'ha "
                f"restituita): {settlement_row['description']!r} {settlement_row['amount']}",
                flush=True,
            )
            rows.append(settlement_row)
    print(f'[pdf_import] righe normalizzate: {rows}', flush=True)
    if not rows:
        raise ValueError("L'estrazione diretta dal PDF non ha trovato nessuna transazione")
    fake_recipe = {'openingBalance': parsed.get('openingBalance'), 'closingBalance': parsed.get('closingBalance')}
    status, message = _reconcile(rows, fake_recipe)
    account_info = {'bankName': parsed.get('bankName')}
    return account_info, rows, status, message


_MAX_RECIPE_ATTEMPTS = 3


def ai_extract_transactions_from_pdf(
    text: str,
    filename: str,
    pdf_bytes: Optional[bytes] = None,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Analizza un campione del testo con l'AI per ricavare una ricetta di
    estrazione (pattern regex + formato data + segno), poi applica quella
    ricetta con un regex a TUTTO il testo. IBAN e numero carta non li chiediamo
    all'AI: li cerchiamo con un regex nella sola intestazione, per evitare di
    prendere per sbaglio l'IBAN di un beneficiario citato dentro una causale
    di bonifico. Se pdf_bytes e' disponibile, rileva anche il segno per
    colonna dalle coordinate REALI del PDF (vedi detect_column_sides_from_pdf),
    piu' affidabile della classificazione amountSign dell'AI per estratti a
    due colonne Uscite/Entrate.

    Prima di richiamare l'AI, prova la ricetta gia' validata in passato per lo
    stesso IBAN (vedi _get_cached_recipe): un conto importato piu' volte non
    deve ripagare ogni volta il costo (e il rischio di errore) di una nuova
    generazione. Se manca, o se non riconcilia piu' (_reconcile), genera una
    ricetta nuova con l'AI e, se il conteggio non riconcilia con i saldi
    dichiarati nel documento, ritenta fino a _MAX_RECIPE_ATTEMPTS volte
    passando all'AI il disallineamento riscontrato. Restituisce
    (account_info, transazioni)."""
    header = text[:_SAMPLE_CHARS]
    print(f'[pdf_import] testo grezzo estratto da {filename} (primi 1500 caratteri): {header[:1500]!r}', flush=True)

    iban = _extract_iban(header)
    column_hints = detect_column_sides_from_pdf(pdf_bytes) if pdf_bytes else None
    # Un rendiconto di carta di credito e' quasi per definizione una lista di
    # spese: ogni riga senza parole chiave ne' colonna che la contraddicano
    # (es. un rimborso/storno) e' un acquisto, non un'entrata - a differenza
    # di un conto corrente dove l'assenza di indicazioni e' ambigua. Bug reale
    # osservato: un acquisto senza parole di direzione veniva importato
    # positivo per mancanza di qualunque altro segnale di segno.
    #
    # Cerchiamo questi segnali solo nei primi credit_card_header_chars
    # caratteri (l'intestazione/anagrafica del documento), non in tutto il
    # campione: un conto corrente normale (es. Fineco) puo' menzionare "carta
    # di credito" dentro la causale di UNA transazione (l'addebito
    # riepilogativo mensile) senza che l'intero documento sia un rendiconto
    # carta - cercarlo ovunque avrebbe forzato negativo anche le entrate vere
    # di quel conto.
    #
    # "carta di credito" da sola non basta: bug reale trovato su un vero
    # rendiconto BNL/Hello Card, che chiama il prodotto "CARTA HELLO CARD" (il
    # nome commerciale della banca, non la dicitura generica) - una regex che
    # cerca solo la frase letterale "carta di credito" non lo riconosce mai,
    # con l'effetto concreto che la riga di pagamento saldo (vedi
    # _CARD_SETTLEMENT_RE) restava negativa invece che positiva. Aggiungiamo
    # altri due segnali generici (non legati al nome commerciale di una banca
    # specifica) tipici SOLO di un prodotto carta, mai di un conto corrente:
    # "limite di utilizzo" (il fido della carta) e "valuta di addebito in
    # c/c" (la data in cui la banca preleva il saldo carta dal conto
    # collegato). Anche questi segnali erano oltre i 200 caratteri originali
    # su questo documento reale (~450-580), quindi allarghiamo la finestra:
    # 800 caratteri restano comunque dentro l'intestazione/anagrafica su tutti
    # gli estratti visti finora (le transazioni vere iniziano molto dopo).
    credit_card_header_chars = 800
    is_credit_card_statement = bool(re.search(
        r'\bcarta\s+di\s+credito\b|\blimite\s+di\s+utilizzo\b|\bvaluta\s+di\s+addebito\s+in\s+c\s*/\s*c\b',
        header[:credit_card_header_chars], re.IGNORECASE,
    ))

    recipe: Optional[Dict[str, Any]] = None
    rows: Optional[List[Dict[str, Any]]] = None
    reconcile_status = 'unknown'
    reconcile_message: Optional[str] = None

    cached_recipe = _get_cached_recipe(iban) if iban else None
    if cached_recipe:
        try:
            cached_rows = extract_transactions_with_recipe(text, cached_recipe, column_hints, is_credit_card_statement)
        except ValueError:
            cached_rows, cache_status, cache_message = [], 'mismatch', 'la ricetta salvata non produce piu\' un match valido'
        else:
            cache_status, cache_message = _reconcile(cached_rows, cached_recipe)
        if cached_rows and cache_status != 'mismatch':
            print(f"[pdf_import] ricetta in cache riusata per IBAN {iban} (bank={cached_recipe.get('bankName')})", flush=True)
            recipe, rows, reconcile_status, reconcile_message = cached_recipe, cached_rows, cache_status, cache_message
        else:
            print(f'[pdf_import] ricetta in cache per IBAN {iban} non valida ({cache_message}), richiedo una nuova ricetta', flush=True)

    if recipe is None:
        previous_recipe: Optional[Dict[str, Any]] = None
        feedback: Optional[str] = None
        for attempt in range(1, _MAX_RECIPE_ATTEMPTS + 1):
            prompt = (
                _build_recipe_prompt(header, filename) if attempt == 1
                else _build_recipe_retry_prompt(header, filename, previous_recipe, feedback)
            )
            content = ai_client.ask_ai(prompt, task_name='casaspese_pdf_recipe', max_tokens=1200)
            candidate_recipe = ai_client.parse_json_object(content)
            print(f'[pdf_import] ricetta AI per {filename} (tentativo {attempt}): {json.dumps(candidate_recipe, ensure_ascii=False)}', flush=True)
            _log_sample_match(candidate_recipe, header)

            try:
                candidate_rows = extract_transactions_with_recipe(text, candidate_recipe, column_hints, is_credit_card_statement)
                attempt_error = None
            except ValueError as e:
                candidate_rows, attempt_error = [], str(e)

            if not candidate_rows:
                if attempt == _MAX_RECIPE_ATTEMPTS:
                    recipe, rows = candidate_recipe, []
                    reconcile_status, reconcile_message = 'mismatch', (
                        attempt_error or "il pattern non ha estratto nessuna transazione dal testo"
                    )
                    break
                previous_recipe = candidate_recipe
                feedback = attempt_error or 'il pattern non ha estratto nessuna transazione'
                print(f'[pdf_import] tentativo {attempt} fallito ({feedback}), ritento con feedback', flush=True)
                continue

            status, message = _reconcile(candidate_rows, candidate_recipe)
            recipe, rows, reconcile_status, reconcile_message = candidate_recipe, candidate_rows, status, message
            if status != 'mismatch' or attempt == _MAX_RECIPE_ATTEMPTS:
                break
            previous_recipe = candidate_recipe
            feedback = message
            print(f'[pdf_import] tentativo {attempt} non riconcilia ({message}), ritento con feedback', flush=True)

    if reconcile_status == 'mismatch' and pdf_bytes:
        print(
            f"[pdf_import] {reconcile_message} Provo il fallback: estrazione diretta del PDF da parte dell'AI.",
            flush=True,
        )
        try:
            fallback_info, fallback_rows, fallback_status, fallback_message = (
                _ai_extract_transactions_direct_from_pdf(pdf_bytes, filename, is_credit_card_statement, text)
            )
        except ValueError as e:
            print(f'[pdf_import] fallback di estrazione diretta fallito: {e}', flush=True)
        else:
            print(
                f'[pdf_import] fallback: estratte {len(fallback_rows)} transazioni direttamente dal PDF, '
                f'riconciliazione: {fallback_status}',
                flush=True,
            )
            # Il fallback legge il documento riga per riga (l'AI vede il layout
            # reale, non applica un'unica regex su tutto il testo): anche quando
            # non riconcilia esattamente, ogni riga resta comunque coerente al suo
            # interno (data/importo/descrizione della STESSA transazione, mai
            # mescolati come puo' succedere con un pattern regex sbagliato che
            # aggancia campi di righe diverse). Per questo usiamo sempre le righe
            # del fallback al posto di quelle regex quando il fallback e' andato
            # a buon fine (anche in caso di mismatch), lasciando che l'utente
            # corregga a mano l'eventuale singola riga sbagliata in fase di
            # approvazione invece di bloccare l'intero import: un mismatch qui e'
            # tipicamente un segno isolato sbagliato, non un disastro strutturale.
            recipe = {'bankName': fallback_info.get('bankName')}
            rows = fallback_rows
            reconcile_status, reconcile_message = fallback_status, fallback_message

    if iban and reconcile_status == 'ok' and recipe.get('pattern'):
        _save_recipe(iban, recipe.get('bankName'), recipe)
        print(f'[pdf_import] ricetta salvata in cache per IBAN {iban}', flush=True)

    if reconcile_status == 'mismatch':
        if not rows:
            print(f'[pdf_import] {reconcile_message}', flush=True)
            raise ValueError(
                f'{reconcile_message} Import bloccato per evitare di salvare transazioni sbagliate: '
                "prova con il file CSV/Excel della banca se disponibile, o contatta l'assistenza."
            )
        print(
            f'[pdf_import] {reconcile_message} (procedo comunque: transazioni disponibili per revisione manuale)',
            flush=True,
        )

    _warn_if_looks_incomplete(text, len(rows))
    sign_warning = _check_same_sign(rows)
    if sign_warning:
        print(f'[pdf_import] {sign_warning}', flush=True)

    account_info = {
        'bankName': recipe.get('bankName'),
        'iban': iban,
        'cardNumber': _extract_card_number(header),
        'signWarning': sign_warning,
        'reconciliationWarning': reconcile_message if reconcile_status == 'mismatch' else None,
    }
    return account_info, rows
