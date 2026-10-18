# GoMitra

AI cattle-health screening for farmers, built on Google Cloud. A Raspberry Pi only captures and uploads photos, short videos and
sound clips; all AI runs in the cloud. The farmer app is a multilingual web app (English, Hindi, Telugu) that says what to do next.

## What it does
- **Skin screening** (lumpy skin disease and foot-and-mouth signs) from photos and camera frames.
- **Cow recognition** by face, so findings are attached to the right cow.
- **Walking and resting check:** pose model finds body points, Gemini scores the gait.
- **Habit trends:** resting more than usual, lying for hours, group chewing down, walking getting worse, and "check this cow first"
  when a sound alert is raised.
- **Sound checks:** call type (possible distress) and eating sounds.
- **Frame agent:** picks the good frames from a clip and routes each to the right model.
- **Ask GoMitra:** a voice-enabled vet assistant (retrieval over vet documents) in three languages, with sources named.
- **SMS alerts:** a text message to the farmer when a new alert is raised (Fast2SMS for India, or Twilio; off until a phone number and provider key are set).
- **Vet report:** a one-page handover note for the vet.

## Google Cloud services
Vertex AI (model endpoint, Gemini 2.5 Flash, embeddings), Cloud Run, Firestore, Cloud Build, Artifact Registry, IAM, Cloud Billing budgets.

## Layout
| Folder | What |
|---|---|
| `serving/` | Model container: HTTP `/predict` for Vertex AI or Cloud Run (weights tracked with Git LFS) |
| `router/` | FastAPI service in layers (`gomitra/api`, `services`, `domain`, `infra`, `core`), tests, and the built web app |
| `pose/` | Pose service (DeepLabCut SuperAnimal-Quadruped) and activity rules |
| `frontend/` | Web app source; `build.py` assembles `router/static/index.html` |
| `deploy/` | PowerShell scripts that build and deploy to Google Cloud and switch the model backend |
| `pi/` | Raspberry Pi uploader |
| `kb_docs/` | Starter vet notes and the loader for licensed source documents |
| `training/` | Model training and evaluation scripts (not part of the deployed app) |
| `docs/` | HLD, LLD, architecture and costs, test cases, jury guide |

## Deploy (Google Cloud)
Set `GOMITRA_GCLOUD` to your `gcloud` executable if it is not on `PATH`, then run `deploy/deploy_backend.ps1` (service account, model service,
router), or `deploy/deploy_serving.ps1`, `deploy_pose.ps1`, `deploy_router.ps1` one by one. `deploy/switch_backend.ps1` points the router at a Vertex AI
endpoint or the Cloud Run model service.

## Tests
```
cd router
pip install -r requirements-dev.txt
python -m pytest              # 152 tests; the 17 that run the models are skipped without serving/models
```

## Status and honest limits
Screening aid, not a diagnosis. The skin model was checked on clear photos (95.9% on 614 held-out photos), not on camera footage or early
cases. The sound models are unvalidated on farms. Habit-trend history in the demo is simulated. The starter vet notes are short notes written for
this project and need review by a veterinarian. See `docs/` for details.

## Design
See docs/HLD.md (components, flows, quality attributes) and docs/LLD.md (layers, patterns, algorithms, tests).

## Credits
The sound models and the best-frame selection approach come from the open-source CattlePlus project (https://github.com/shashi007-hub/livestock-monitoring) and its teammates' repositories. Models and datasets keep their own licences.

