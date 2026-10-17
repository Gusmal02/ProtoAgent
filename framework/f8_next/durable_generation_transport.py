"""Network adapter over durable intents; admission remains a separate host step.

No constructor issues grants or resets budget. No retry after uncertain send.
Credentials stay only in a request header and are never journalled.
"""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from generation_transaction import GenerationTransaction, TransactionError, sha


class UncertainGeneration(RuntimeError): pass


class DurableGenerationTransport:
    def __init__(self, ledger, *, send, actor, entity, revision):
        self.ledger = ledger
        self.send = send
        self.actor = actor; self.entity = entity; self.revision = revision

    def submit(self, identity, request):
        row = self.ledger.reserve(identity, self.actor, self.entity, self.revision, request)
        if row['state'] in ('dispatching','receiving','uncertain'):
            self.ledger.recover(identity)
            raise UncertainGeneration('reconciliation required, no resend')
        if row['state'] in ('response_durable','verified','admitted'):
            if sha(row['response']) != row['hash']: raise TransactionError('stored response corrupted')
            return json.loads(row['response'])
        if row['state'] != 'reserved': raise TransactionError('intent terminal; a new decision/ID is required')
        self.ledger.begin_dispatch(identity)
        def part(ordinal, data): self.ledger.receive_part(identity, ordinal, data)
        try:
            response_hash = self.send(request, part)
            self.ledger.commit_response(identity, response_hash)
        except Exception:
            self.ledger.recover(identity)
            raise UncertainGeneration('provider result uncertain; budget preserved, no automatic resend') from None
        return json.loads(self.ledger.row(identity)['response'])


class GeminiStreamingTransport:
    def __init__(self, api_key, *, model='gemini-3.1-flash-lite', timeout=45):
        if model != 'gemini-3.1-flash-lite': raise ValueError('model not approved for this block')
        self._key = api_key; self.model = model; self.timeout = timeout

    def __call__(self, document, persist_part):
        config = document.get('generationConfig', {})
        if (type(config.get('maxOutputTokens')) is not int or not 1 <= config['maxOutputTokens'] <= 8192
                or 'tools' in document or config.get('responseMimeType') != 'application/json'):
            raise ValueError('request outside approved generation policy')
        # This API returns a normal generateContent response. Read it in bounded
        # byte chunks and durably spool each one; do not confuse this with SSE.
        request = Request('https://generativelanguage.googleapis.com/v1beta/models/'+self.model+':generateContent',
                          data=json.dumps(document).encode(), headers={'x-goog-api-key':self._key,'Content-Type':'application/json'})
        import hashlib
        digest = hashlib.sha256(); length = 0; ordinal = 0
        try:
            with urlopen(request, timeout=self.timeout) as response:
                while True:
                    chunk = response.read(16384)
                    if not chunk: break
                    length += len(chunk)
                    if length > 524288: raise ValueError('response size limit')
                    persist_part(ordinal, chunk); digest.update(chunk); ordinal += 1
        except (HTTPError, URLError, TimeoutError, ValueError):
            # Do not print raw provider bodies, credentials or claim that an
            # HTTP failure proves that generation consumed nothing.
            raise UncertainGeneration('provider interrupted or unavailable') from None
        return digest.hexdigest()
