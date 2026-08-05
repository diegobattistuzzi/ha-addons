# Guida operativa

Questa guida spiega il funzionamento generale dell'app e alcuni concetti che non sono ovvi dall'interfaccia, in particolare come registrare correttamente le transazioni perché il **Bilancio tra persone** risulti giusto.

## Funzionamento generale

L'app è organizzata nelle sezioni della barra laterale:

- **Dashboard** — riepilogo del mese in corso, con scorciatoie per aggiungere una spesa o importare un estratto conto.
- **Transazioni** — il registro principale: elenco e filtro di tutte le transazioni, inserimento manuale, import estratto conto, aggiunta rapida via AI (testo libero), revisione delle categorie suggerite dall'AI.
- **Report** — andamento nel tempo (grafici) e un builder per report personalizzati.
- **Assistente** — riepilogo narrativo del mese scritto dall'AI, rilevamento di spese anomale (picchi per categoria, nuovi esercenti) e una chat per fare domande sui dati o costruire/salvare un report personalizzato.
- **Bilancio** — chi ha versato/speso cosa, per mese o su tutto il periodo (vedi più sotto).
- **Documenti** — copertura documentale (quali mesi/conti hanno l'estratto conto caricato) e archivio dei file importati.
- **Messaggi email** — ricevute d'acquisto (PayPal, Amazon, negozi) intercettate via email e il loro stato di abbinamento automatico alle transazioni.
- **Persone** — anagrafica dei membri della famiglia; da qui si genera anche l'accesso mobile via QR (vedi sotto).
- **Conti** — anagrafica dei conti (correnti, carte, contanti, buoni pasto): qui si distingue un conto personale da uno comune.
- **Categorie** — albero delle categorie di spesa/entrata/trasferimento, con parole chiave usate dalla categorizzazione automatica.
- **Regole** — regole personalizzate per riconoscere automaticamente le transazioni ricorrenti (vedi "Traccia spese" più sotto).
- **Impostazioni** — wizard di configurazione iniziale (persone, conti, categorie, chiave AI).

## Gestione del conto comune

Un conto si crea/modifica da **Conti → Aggiungi conto**. Il campo chiave è la **proprietà (ownership)**:

- **Comune (shared)** — è il fondo condiviso. Le spese pagate da qui sono spese di famiglia per tutti; le entrate sono versamenti di chi le ha fatte. Visibile a tutti.
- **Personale (personal)** — richiede di indicare un **intestatario** (una persona). Le sue transazioni sono automaticamente private: visibili solo all'intestatario, non compaiono come spese di famiglia a meno che non vengano esplicitamente segnate come tali.

Per le carte di credito c'è anche il **conto di appoggio** (`settlement account`): il conto corrente da cui parte l'addebito mensile riepilogativo della carta. Serve solo per evitare il doppio conteggio quando importi l'estratto conto del c/c: l'app riconosce l'addebito unico e propone di segnarlo come trasferimento interno, dato che la spesa è già registrata voce per voce sulla carta.

## Caricamento in conto comune (come entrano le transazioni)

Ci sono quattro modi per registrare movimenti su un conto (comune o personale), oltre al bonifico/versamento descritto sotto:

1. **Import estratto conto** (Transazioni → "Importa estratto conto") — carica PDF, CSV, Excel, buoni pasto o file CBI. L'app riconosce il conto dall'IBAN quando possibile, gestisce estratti a due colonne (entrate/uscite), causali su più righe ed estratti carta di credito. Le righe duplicate (stesso conto, data, importo, descrizione) vengono scartate automaticamente. Le transazioni importate entrano **da confermare** e passano subito per la categorizzazione automatica (vedi "Traccia spese").
2. **Scansione scontrino o dettatura vocale da mobile** ("Scansiona" nell'app mobile, vedi sotto) — foto dello scontrino o frase vocale ("23€ pizza ieri sera con amex"): l'AI propone una bozza (importo, esercente, data, categoria) che l'utente rivede e conferma. Solo al salvataggio la transazione viene creata, già confermata.
3. **Inserimento manuale da desktop** (Transazioni → "+ Aggiungi") — form completo: data, importo, descrizione, conto, categoria, destinazione (famiglia/personale/split), chi ha pagato/con chi è divisa, contanti, rimborsabile, note, allegati. C'è anche un campo di testo libero ("AI quick add") che precompila lo stesso form da linguaggio naturale.
4. **Bonifico/versamento verso il conto comune** — non è un modo per "aggiungere" spesa, ma per spostare provvista da un conto personale al fondo comune. Va gestito con attenzione particolare, vedi la sezione seguente.

### Trasferimenti tra conti propri (es. "verso il fondo comune 600€")

Un bonifico da un conto personale al conto comune genera **due righe**, una per ogni estratto conto importato. Vanno categorizzate in modo diverso:

| Riga | Conto | Importo | Categoria |
|---|---|---|---|
| Uscita | Conto personale | −600€ | **Trasferimenti** |
| Entrata | Conto comune | +600€ | *non* Trasferimenti — categoria normale, con "Pagato da" compilato |

Perché diverse:

- Qualsiasi riga con categoria **Trasferimenti** viene **esclusa** dal calcolo del bilancio (non è una spesa né un'entrata reale, è solo spostare i propri soldi).
- Se marchi *anche* l'entrata sul conto comune come Trasferimenti, il versamento sparisce dal bilancio: sembra che quella persona non abbia mai messo nulla nel fondo comune.
- Se invece lasci *anche* l'uscita dal conto personale con categoria normale, verrebbe contata come una spesa di famiglia divisa fra tutti — la stessa cifra finirebbe doppia (una volta come versamento, una volta come spesa comune).

**Regola pratica:** solo l'uscita dal conto personale va marcata Trasferimenti. L'entrata sul conto comune resta "normale" (categoria libera o nessuna), con il campo **Pagato da** compilato: è quello il segnale che alimenta il fondo comune per conto di quella persona.

## Traccia spese: da importata a confermata

Ogni transazione ha uno stato **confermata / da confermare**:

- Le transazioni **importate** da estratto conto entrano sempre da confermare, ed entrano nella pipeline di categorizzazione automatica:
  1. si controlla prima se una **regola** (pagina **Regole**) corrisponde alla descrizione (testo o regex) e al segno dell'importo: in caso di match la transazione viene categorizzata **e già confermata** direttamente, perché è una scelta esplicita dell'utente — non un suggerimento. Una regola può anche impostare destinazione (famiglia/personale/split), chi ha pagato o con chi è divisa. Utile per movimenti ricorrenti (bollette, stipendio, abbonamenti) che altrimenti andrebbero riconfermati ogni mese;
  2. se nessuna regola corrisponde e la causale cita l'IBAN di un altro conto già censito, viene taggata come **Trasferimenti** (probabile giroconto interno);
  3. altrimenti si cerca una corrispondenza tra le parole chiave delle categorie;
  4. le transazioni rimaste vengono mandate all'AI, che propone una categoria con un livello di confidenza.
  Nei punti 2-4 si tratta solo di un **suggerimento** (`ai_category_id`): la transazione resta da confermare finché non la approvi. Solo le regole (punto 1) confermano subito.
- In **Transazioni** le righe con suggerimento AI mostrano un'icona ✦ e compaiono in un banner in alto ("N categorizzate da AI") con pulsanti "Mostra" e "Approva tutte". Riga per riga c'è un ✓ per accettare il singolo suggerimento; selezionando più righe si può confermare o scartare il suggerimento in blocco.
- Le transazioni **inserite manualmente** (form desktop o scansione scontrino) sono già confermate al salvataggio: l'utente ha già validato i dati inserendoli.
- **Abbinamento email ricevute** (pagina "Messaggi email"): l'app intercetta le email di conferma acquisto (PayPal, Amazon, negozi), estrae con l'AI esercente/importo/data/descrizione e prova ad abbinarle a una transazione già importata con lo stesso importo e una data vicina (±5 giorni). Se trova corrispondenza, arricchisce la transazione con il nome reale dell'esercente e delle note — utile perché l'estratto conto spesso mostra solo una sigla generica ("PAGAMENTO POS ABC123"), mentre l'email dice cosa hai comprato davvero, senza lavoro manuale. Se non trova corrispondenza al momento, il tentativo viene ripetuto al prossimo import, oppure manualmente col pulsante "Riabbina mail".

## App mobile (QR code)

Da **Persone → 📱 (accesso mobile)** si genera un QR code/link personale per un membro della famiglia: inquadrandolo (o aprendo il link) si installa una PWA sul telefono, senza bisogno della rete di casa/Home Assistant. Ha due sole schermate:

- **Scansiona** — foto di uno scontrino o dettatura vocale della spesa; l'AI propone una bozza che l'utente conferma prima di salvare. Pensata per registrare la spesa sul momento, al negozio, invece di doverla ricostruire dopo dall'estratto conto.
- **Transazioni** — elenco semplificato delle transazioni del mese corrente, con possibilità di aprirle e correggerle (importo, descrizione, data, categoria, conto).

I QR/token si possono revocare in qualsiasi momento dalla stessa pagina Persone (lista sotto al QR, pulsante ✕).

## Come si legge il Bilancio

Nella pagina **Bilancio** ogni persona ha tre voci:

- **Versamenti al comune** — quanto ha messo nel conto comune (bonifici, come sopra).
- **Quota spese comuni** — la sua quota delle spese di famiglia pagate (da qualunque conto).
- **Spese personali** — spese personali pagate però con soldi del conto comune (erodono il fondo comune, quindi vanno "restituite").

Il **saldo netto** = Versamenti − Quota spese comuni − Spese personali. È il numero che dice se una persona ha messo/speso per la famiglia più o meno della sua parte: se è positivo, è lei ad avere credito verso l'altra persona.

## Spese pagate a metà tra due persone (split)

Se una spesa non è né "di famiglia" (divisa equamente tra tutti) né "personale", puoi indicarla come **split**: si divide solo fra chi ha pagato e la persona indicata, secondo la quota (`split_ratio`) di chi ha pagato. Chi ha pagato viene accreditato per l'intero importo (come un versamento), non solo per la propria quota — ha anticipato lui i soldi.

## Checklist quando qualcosa nel bilancio non torna

1. Il campo **Pagato da** è compilato su tutte le transazioni rilevanti? Senza, non vengono conteggiate.
2. Le righe di trasferimento tra conti propri hanno **solo la riga di uscita** marcata Trasferimenti, non anche l'entrata?
3. Le spese personali pagate dal conto comune hanno la destinazione corretta ("personale"), così da risultare come `personalSpent` e non come spesa di famiglia?
