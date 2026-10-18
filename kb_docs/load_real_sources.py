"""Download the licensed veterinary PDFs listed in real_sources/SOURCES.md and load them into the assistant.

  python kb_docs/load_real_sources.py https://YOUR-SERVICE.run.app ADMIN_KEY

Needs: pip install requests. The router splits each PDF, embeds it with Vertex AI embeddings and stores it in Firestore.
"""
import base64
import os
import sys

import requests

DOCS = [("FAO (2017) Lumpy skin disease: a field manual for veterinarians", "fao_lumpy_skin_disease_manual_2017.pdf",
         "https://openknowledge.fao.org/server/api/core/bitstreams/1c277d5a-b2eb-42f3-a32a-9c71fde089f0/content")]


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    url, key = sys.argv[1].rstrip("/"), sys.argv[2]
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "real_sources")
    os.makedirs(here, exist_ok=True)
    for source, name, link in DOCS:
        path = os.path.join(here, name)
        if not os.path.exists(path):
            r = requests.get(link, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            open(path, "wb").write(r.content)
        pdf = base64.b64encode(open(path, "rb").read()).decode()
        r = requests.post(url + "/api/admin/kb", headers={"x-admin-key": key}, json={"source": source, "pdf": pdf}, timeout=280)
        print(source, "->", r.status_code, r.json())


if __name__ == "__main__":
    main()
