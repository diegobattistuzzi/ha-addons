import base64
import json
import re

import httpx

from . import config

# Schema semplice per ai_task.generate_data: un solo campo di testo con la
# risposta grezza. Evita selettori annidati (object/multiple/fields) che non
# tutte le integrazioni AI Task sanno gestire in modo affidabile.
_HA_STRUCTURE = {
    'result_text': {
        'description': 'Risposta come stringa di testo (secondo il formato richiesto nelle istruzioni)',
        'required': True,
        'selector': {'text': {}},
    },
}


def ask_ai(prompt: str, task_name: str = 'casaspese_task', max_tokens: int = 4000) -> str:
    """Chiede una risposta testuale all'AI configurata.

    Preferisce la chiave OpenAI/Anthropic dell'addon (affidabile e testabile);
    se non configurata, ripiega su ai_task.generate_data di Home Assistant.
    """
    if config.OPENAI_API_KEY or config.ANTHROPIC_API_KEY:
        if config.AI_PROVIDER == 'anthropic' and config.ANTHROPIC_API_KEY:
            return _call_anthropic(prompt, max_tokens)
        return _call_openai(prompt, max_tokens)
    return _call_ha_ai_task(prompt, task_name)


def _snippet(content: str, length: int = 300) -> str:
    text = (content or '').strip()
    if not text:
        return '(risposta vuota)'
    return text[:length] + ('...' if len(text) > length else '')


def _log_failure(kind: str, content: str, error: str) -> None:
    """Scrive su stdout (visibile nel log dell'addon in Home Assistant) la
    risposta completa dell'AI quando il parsing fallisce, per poter capire
    cosa e' successo senza dover riprodurre il problema."""
    print(f'[ai_client] {kind}: {error}\n[ai_client] risposta completa:\n{content}', flush=True)


_VALID_JSON_ESCAPES = set('"\\/bfnrtu')


def _fix_invalid_escapes(content: str) -> str:
    """Quando l'AI restituisce un'espressione regolare dentro una stringa JSON,
    a volte scrive un backslash di troppo poco (es. "\\s" invece di "\\\\s"
    nel JSON), producendo un escape JSON non valido - probabilmente perche' i
    prompt mostrano esempi di sintassi regex non json-escaped e l'AI li
    ricopia alla lettera. Raddoppia i backslash seguiti da un carattere che
    non e' un escape JSON valido, lasciando intatti quelli gia' corretti."""
    return re.sub(
        r'\\(.)',
        lambda m: m.group(0) if m.group(1) in _VALID_JSON_ESCAPES else '\\\\' + m.group(1),
        content,
        flags=re.DOTALL,
    )


def parse_json_object(content: str) -> dict:
    cleaned = _strip_markdown_fences(content)
    match = re.search(r'\{[\s\S]*\}', cleaned)
    if not match:
        error = "L'AI non ha restituito un oggetto JSON valido"
        _log_failure(error, content, error)
        raise ValueError(f"{error}. Risposta ricevuta: {_snippet(content)}")
    raw = match.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass  # prova a recuperare sotto: backslash non correttamente raddoppiati
    try:
        return json.loads(_fix_invalid_escapes(raw))
    except json.JSONDecodeError as e:
        error = f"L'AI ha restituito un oggetto JSON non valido ({e})"
        _log_failure(error, content, error)
        raise ValueError(f"{error}. Risposta ricevuta: {_snippet(content)}")


def parse_json_array(content: str) -> list:
    """Estrae l'array JSON dalla risposta dell'AI, tollerando risposte troncate
    (limite di max_tokens raggiunto a meta' di un oggetto): recupera gli
    elementi completi scartando solo l'ultimo se incompleto."""
    cleaned = _strip_markdown_fences(content)
    start = cleaned.find('[')
    if start == -1:
        error = "L'AI non ha restituito un array JSON valido"
        _log_failure(error, content, error)
        raise ValueError(f"{error}. Risposta ricevuta: {_snippet(content)}")

    end = _find_matching_bracket(cleaned, start)
    if end is not None:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            pass  # non valido nonostante la parentesi chiusa: prova a recuperare sotto

    last_object_end = cleaned.rfind('}', start)
    if last_object_end != -1:
        try:
            rows = json.loads(cleaned[start:last_object_end + 1] + ']')
            print(
                f'[ai_client] risposta AI troncata (max_tokens raggiunto): recuperati {len(rows)} '
                "elementi completi, scartato l'ultimo incompleto.",
                flush=True,
            )
            return rows
        except json.JSONDecodeError:
            pass

    error = "L'AI non ha restituito un array JSON valido"
    _log_failure(error, content, error)
    raise ValueError(f"{error}. Risposta ricevuta: {_snippet(content)}")


def _find_matching_bracket(text: str, start: int):
    """Trova l'indice della ']' che chiude la '[' in posizione start, gestendo
    correttamente le stringhe (per non confondere parentesi dentro i valori)."""
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                return i
    return None


def _strip_markdown_fences(content: str) -> str:
    cleaned = re.sub(r'^```(?:json)?\n?', '', content.strip())
    return re.sub(r'\n?```$', '', cleaned)


# ── Chiave OpenAI/Anthropic configurata nell'addon ──────────────────────────

def _call_openai(prompt: str, max_tokens: int) -> str:
    try:
        response = httpx.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {config.OPENAI_API_KEY}'},
            json={
                'model': config.AI_MODEL or 'gpt-4o-mini',
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': max_tokens,
            },
            timeout=120.0,
        )
    except httpx.TimeoutException:
        raise ValueError("Timeout nella chiamata a OpenAI: il servizio non ha risposto in tempo. Riprova, oppure importa un file piu' corto.")
    except httpx.HTTPError as e:
        raise ValueError(f'Impossibile raggiungere OpenAI ({e}).')
    if response.status_code != 200:
        raise ValueError(f'OpenAI API error: {response.status_code}')
    return response.json()['choices'][0]['message']['content'].strip()


def _call_anthropic(prompt: str, max_tokens: int) -> str:
    try:
        response = httpx.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': config.ANTHROPIC_API_KEY,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            },
            json={
                'model': 'claude-haiku-4-5-20251001',
                'max_tokens': max_tokens,
                'messages': [{'role': 'user', 'content': prompt}],
            },
            timeout=120.0,
        )
    except httpx.TimeoutException:
        raise ValueError("Timeout nella chiamata ad Anthropic: il servizio non ha risposto in tempo. Riprova, oppure importa un file piu' corto.")
    except httpx.HTTPError as e:
        raise ValueError(f'Impossibile raggiungere Anthropic ({e}).')
    if response.status_code != 200:
        raise ValueError(f'Anthropic API error: {response.status_code}')
    return response.json()['content'][0]['text'].strip()


def ask_ai_with_pdf(prompt: str, pdf_bytes: bytes, filename: str, max_tokens: int = 8000) -> str:
    """Come ask_ai, ma allega anche il PDF originale (base64) come documento,
    invece di un semplice campione di testo appiattito - usato solo come
    fallback quando il riconoscimento tramite regex fallisce ripetutamente,
    per lasciare che l'AI legga direttamente il layout reale del documento
    (colonne, posizione dell'importo) invece di ragionare su testo estratto
    che ha gia' perso quell'informazione. Richiede la Responses API di
    OpenAI (content type 'input_file', supportato dai modelli con vision
    come gpt-4o/gpt-4o-mini): Anthropic e il fallback ai_task di Home
    Assistant non sono supportati per questo percorso."""
    if not config.OPENAI_API_KEY or config.AI_PROVIDER == 'anthropic':
        raise ValueError(
            "Il fallback di estrazione diretta dal PDF e' disponibile solo con provider OpenAI configurato."
        )
    b64 = base64.b64encode(pdf_bytes).decode('ascii')
    try:
        response = httpx.post(
            'https://api.openai.com/v1/responses',
            headers={'Authorization': f'Bearer {config.OPENAI_API_KEY}'},
            json={
                'model': config.AI_MODEL or 'gpt-4o-mini',
                'input': [{
                    'role': 'user',
                    'content': [
                        {'type': 'input_text', 'text': prompt},
                        {
                            'type': 'input_file',
                            'filename': filename,
                            'file_data': f'data:application/pdf;base64,{b64}',
                        },
                    ],
                }],
                'max_output_tokens': max_tokens,
            },
            timeout=180.0,
        )
    except httpx.TimeoutException:
        raise ValueError(
            "Timeout nella chiamata a OpenAI (estrazione diretta dal PDF): il servizio non ha risposto in tempo."
        )
    except httpx.HTTPError as e:
        raise ValueError(f'Impossibile raggiungere OpenAI ({e}).')
    if response.status_code != 200:
        raise ValueError(f'OpenAI API error (estrazione diretta dal PDF): {response.status_code} {response.text[:300]}')
    return _extract_responses_output_text(response.json())


def ask_ai_with_image(prompt: str, image_bytes: bytes, filename: str, max_tokens: int = 800) -> str:
    """Come ask_ai_with_pdf, ma per una foto di scontrino: usa la Responses API
    di OpenAI con un content 'input_image' (vision), stesso vincolo di
    provider di ask_ai_with_pdf (solo OpenAI, non Anthropic ne' HA ai_task)."""
    if not config.OPENAI_API_KEY or config.AI_PROVIDER == 'anthropic':
        raise ValueError(
            "La lettura degli scontrini via foto e' disponibile solo con provider OpenAI configurato."
        )
    mime_type = 'image/png' if filename.lower().endswith('.png') else 'image/jpeg'
    b64 = base64.b64encode(image_bytes).decode('ascii')
    try:
        response = httpx.post(
            'https://api.openai.com/v1/responses',
            headers={'Authorization': f'Bearer {config.OPENAI_API_KEY}'},
            json={
                'model': config.AI_MODEL or 'gpt-4o-mini',
                'input': [{
                    'role': 'user',
                    'content': [
                        {'type': 'input_text', 'text': prompt},
                        {'type': 'input_image', 'image_url': f'data:{mime_type};base64,{b64}'},
                    ],
                }],
                'max_output_tokens': max_tokens,
            },
            timeout=120.0,
        )
    except httpx.TimeoutException:
        raise ValueError('Timeout nella chiamata a OpenAI (lettura scontrino): il servizio non ha risposto in tempo.')
    except httpx.HTTPError as e:
        raise ValueError(f'Impossibile raggiungere OpenAI ({e}).')
    if response.status_code != 200:
        raise ValueError(f'OpenAI API error (lettura scontrino): {response.status_code} {response.text[:300]}')
    return _extract_responses_output_text(response.json())


def _extract_responses_output_text(payload: dict) -> str:
    """Estrae il testo di risposta dal formato della Responses API (diverso
    da Chat Completions: la risposta e' una lista di 'output' eterogenei,
    il testo vero sta nell'item di tipo 'message' -> content di tipo
    'output_text')."""
    for item in payload.get('output', []):
        if item.get('type') != 'message':
            continue
        for part in item.get('content', []):
            if part.get('type') == 'output_text' and part.get('text'):
                return part['text'].strip()
    raise ValueError("L'AI non ha restituito testo nella risposta (estrazione diretta dal PDF)")


# ── Fallback: ai_task.generate_data di Home Assistant ───────────────────────

def _call_ha_ai_task(prompt: str, task_name: str) -> str:
    if not config.SUPERVISOR_TOKEN:
        raise ValueError(
            "Nessuna chiave AI configurata nell'addon e funzione ai_task non disponibile in questo ambiente "
            "(fuori da Home Assistant). Aggiungi una chiave OpenAI/Anthropic in Impostazioni -> Add-on -> "
            "CasaSpese -> Configurazione."
        )

    try:
        response = httpx.post(
            'http://supervisor/core/api/services/ai_task/generate_data?return_response',
            headers={
                'Authorization': f'Bearer {config.SUPERVISOR_TOKEN}',
                'Content-Type': 'application/json',
            },
            json={
                'task_name': task_name,
                'instructions': prompt,
                'structure': _HA_STRUCTURE,
            },
            timeout=90.0,
        )
    except httpx.HTTPError as e:
        raise ValueError(
            f"Impossibile raggiungere il servizio AI di Home Assistant ({e}). Configura una chiave OpenAI/Anthropic "
            "nell'addon oppure un'integrazione AI Task in Home Assistant."
        )

    if response.status_code != 200:
        try:
            detail = response.json().get('message') or response.text
        except Exception:
            detail = response.text
        raise ValueError(f"Errore dal servizio AI di Home Assistant (HTTP {response.status_code}): {detail}")

    payload = response.json()
    service_response = payload.get('service_response', payload) if isinstance(payload, dict) else {}
    data_out = service_response.get('data', service_response) if isinstance(service_response, dict) else {}
    raw = data_out.get('result_text') if isinstance(data_out, dict) else None
    if not raw or not isinstance(raw, str):
        raise ValueError("L'AI di Home Assistant non ha restituito il campo result_text atteso")
    return raw
