# Changelog

## 1.0.24

- Refactor del backend: `server.py` diviso in router FastAPI per dominio (`backend/routers/`), per manutenibilità.

## 1.0.23

- Aggiunta prima versione della reportistica basata su AI.
- Fix del link di download allegati quando l'app viene aperta da un link mobile con hash.

## 1.0.21

- Aggiunta condivisione conti tra persone e distinzione tra spese personali e comuni.

## 1.0.18

- Pubblicazione automatica dei sorgenti dell'add-on su ha-addons via CI al push sul branch `publish`.

## 1.0.16

- Aggiunta la guida in-app.

## 1.0.15

- Miglioramenti a import estratti conto e report.
- Aggiunto supporto PWA (installazione come app, accesso mobile).

## 1.0.13

- Abbinamento ricevute email, categorizzazione AI e gestione segno importi migliorati.

## 1.0.7

- Rimosso il vecchio backend Node.js (dismesso a favore di Python/FastAPI).
- Aggiunta la cronologia messaggi AI.

## 1.0.5

- Import estratti conto, categorizzazione AI e ricezione ricevute via email.

## 1.0.3

- Aggiunta la gestione delle regole di categorizzazione automatica.

## 1.0.2

- Fix della comunicazione con l'Ingress di Home Assistant.
- Aggiunta la visibilità delle transazioni per persona e l'archiviazione documenti.

## 1.0.0

- Prima versione dell'add-on.
