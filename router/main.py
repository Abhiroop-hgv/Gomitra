"""GoMitra router entry point: `uvicorn main:app`. The application lives in the `gomitra` package (see docs/LLD.md)."""
from gomitra.api.app import app  # noqa: F401
