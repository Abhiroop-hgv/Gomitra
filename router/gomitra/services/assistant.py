"""Ask GoMitra: answers from the vet documents, and the admin operations on the document library."""
import base64

from gomitra.context import kb, store
from gomitra.core import tracing as trace
from gomitra.errors import BadRequest, UpstreamError
from gomitra.services import messages
from gomitra.services.kb import pdf_text


def ask(question, lang="en", cow_id=None):
    """Grounded answer in the farmer's language, with the sources named. -> {"answer", "sources", "grounded", "trace"}"""
    if lang not in messages.LANGS:
        raise BadRequest("lang must be en, hi or te")
    name = (store.get("cows", cow_id) or {}).get("name") if cow_id else None
    try:
        trace.start()
        out = kb.answer(question.strip(), lang, name)
        out["trace"] = trace.get()
        return out
    except Exception as e:
        raise UpstreamError(f"assistant unavailable: {type(e).__name__}")


def add_document(source, text=None, pdf_b64=None):
    """Index a document (plain text or a base64 PDF). Re-adding a source replaces its old pieces. -> number of pieces."""
    body = text or pdf_text(base64.b64decode(pdf_b64 or ""))
    return kb.add(source, body)


def remove_document(source):
    return kb.remove(source)


def sources():
    return kb.sources()
