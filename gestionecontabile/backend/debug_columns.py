"""Script diagnostico: mostra come viene estratto un PDF con le coordinate
reali (vedi pdf_import.detect_column_sides_from_pdf), per verificare il
rilevamento della colonna Uscite/Entrate su un file reale.

Uso:
    python backend/debug_columns.py "percorso/al/file.pdf"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.pdf_import import (
    _collect_text_fragments,
    _group_fragments_into_rows,
    _find_column_x_positions,
    _AMOUNT_TOKEN_RE,
    _parse_amount,
    _strip_currency,
    detect_column_sides_from_pdf,
    extract_pdf_text,
    read_pdf,
)

sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def main(path: str):
    data = Path(path).read_bytes()

    print(f"=== Analisi coordinate: {path} ===\n")
    reader = read_pdf(data)

    column_x = None
    for page_num, page in enumerate(reader.pages, 1):
        fragments = _collect_text_fragments(page)
        rows = _group_fragments_into_rows(fragments)
        page_columns = _find_column_x_positions(rows)
        if page_columns:
            column_x = page_columns
            print(f"[pagina {page_num}] intestazione colonna trovata: {page_columns}")

        print(f"[pagina {page_num}] {len(rows)} righe rilevate, {len(fragments)} frammenti di testo")
        for row in rows[:15]:
            row_text = ' | '.join(f"{text!r}@x={x:.1f}" for x, text in row)
            print(f"   riga: {row_text}")
        if len(rows) > 15:
            print(f"   ... e altre {len(rows) - 15} righe")

        if column_x:
            for row in rows:
                for x, raw_text in row:
                    text = _strip_currency(raw_text)
                    if _AMOUNT_TOKEN_RE.match(text):
                        value = _parse_amount(text)
                        if value is None:
                            continue
                        neg_d = abs(x - column_x['negative'])
                        pos_d = abs(x - column_x['positive'])
                        side = 'negative (Uscite)' if neg_d <= pos_d else 'positive (Entrate)'
                        row_desc = ' '.join(t for _, t in row if t != text)[:60]
                        print(f"   importo {text!r} x={x:.1f} -> {side}   [{row_desc}]")
        print()

    print("=== Riepilogo: detect_column_sides_from_pdf ===")
    hints = detect_column_sides_from_pdf(data)
    if hints is None:
        print("Nessuna intestazione di colonna riconosciuta (None)")
    else:
        for value, side in hints:
            print(f"  {value:>10.2f}  ->  {side}")

    print("\n=== Testo estratto (extract_pdf_text, plain, primi 2000 caratteri) ===")
    print(extract_pdf_text(data)[:2000])


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Uso: python backend/debug_columns.py <percorso.pdf>")
        sys.exit(1)
    main(sys.argv[1])
