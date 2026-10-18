# Real veterinary sources used by the Ask GoMitra assistant

The PDFs are not kept in this repository. `load_real_sources.py` downloads them from their publishers and loads them into the
assistant (Vertex AI embeddings, stored in Firestore). Every answer names the document it used.

| Loaded | Document | Publisher | Terms (checked in the document) |
|---|---|---|---|
| Yes | *Lumpy skin disease: a field manual for veterinarians*, FAO Animal Production and Health Manual No. 20 (2017). https://openknowledge.fao.org/server/api/core/bitstreams/1c277d5a-b2eb-42f3-a32a-9c71fde089f0/content | FAO | "(c) FAO, 2017. FAO encourages the use, reproduction and dissemination of material in this information product ... for private study, research and teaching purposes, or for use in non-commercial products or services", with acknowledgement. |
| No | *Bloat in Cattle*, Alberta Agriculture (2003) | Government of Alberta | All rights reserved; storing it in a retrieval system needs written permission. **Not used.** |
| No | Unit 10 factsheet on lameness in cattle and sheep, Hwb Wales | Welsh Government | No licence statement in the document. **Not used until the terms are confirmed.** |
| No | ICAR-NIVEDI mastitis leaflet (2019) | ICAR-NIVEDI | Could not be reached from the build machine; terms not checked. |

The short "GoMitra starter notes" are written by the team for this project and are not published veterinary material. A veterinarian
must review all content before any real use. These documents give general information, not a diagnosis or a treatment plan.
