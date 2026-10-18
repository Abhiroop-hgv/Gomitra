# GoMitra: low-level design (router)

## 1. Layers and dependency rule
Dependencies point downwards only: `api -> services -> domain / infra -> core`. `domain` never imports a service, the web framework or a
cloud client, so every rule is testable with plain Python.

```
router/
  main.py                   entry point: from gomitra.api.app import app
  gomitra/
    config.py               settings and tunable constants (env read once)
    errors.py               AppError and subclasses (400/403/404/413/415/422/502)
    context.py              composition root: store, infer, kb singletons
    core/                   tracing.py (measured steps), ratelimit.py, util.py
    infra/                  store.py (Memory | Firestore), inference.py (Vertex | Cloud Run | local)
    domain/                 rules.py, trends.py, suspects.py, agent.py, matching.py   (pure logic)
    services/               cows, analysis, audio, posture, ingest, alerts, assistant, system, demo,
                            messages, kb, gait, report   (use-cases)
    api/                    app.py (create_app, guard, error mapping), deps.py, schemas.py, routes/*
  tests/unit, tests/api     pytest
```

## 2. Design decisions
| Principle / pattern | Where |
|---|---|
| Single responsibility | One module per use-case; routes only parse and delegate |
| Repository | `infra/store.py`: `Memory` and `Firestore` share put/get/update/list/list_where/delete and batch calls |
| Strategy | `infra/inference.py`: `INFER_BACKEND` selects Vertex AI, Cloud Run or in-process models behind `Infer.predict` |
| Dependency inversion | Services use `context.store/infer/kb`; tests choose the in-memory store and local models by environment |
| Pure domain, thin edges | Rules in `domain/` take dicts and return dicts; no I/O |
| Errors as values at the edge | Services raise `AppError` subclasses; `api/app.py` maps them to HTTP in one handler |
| Graceful degradation | Gemini failure -> `messages.template`; pose failure -> Gemini-only gait; both visible in the result |
| Observability | `core/tracing.py`: `with step(service, detail)` times each external call; endpoints return the list |
| Fail cheap | Rate limiter per visitor; frame agent drops frames before any model call; caches (1-minute eating trend) |

## 3. Key algorithms (all thresholds in the module that owns them)
**Skin finding** (`rules.skin_finding`): best of lumpy / foot-and-mouth with P >= 0.60 and above normal; severity high if P >= 0.85
or foot-and-mouth. Photos alert at once; camera frames need 2 of the last 5 sightings (`rules.confirmed`).

**Cow matching** (`matching.match_face`): cosine similarity of the sharpest usable face with each registered embedding; accept at
>= 0.69; ear-tag OCR as fallback; a face is only used inside a cow's box.

**Frame agent** (`agent.py`): screen (dark, blurred, duplicate, keep the 8 sharpest) -> assess each frame from detector output (cut off by
edge, blocked by another cow, size, side-on aspect 1.3-2.4) -> choose (best face frame, best skin frame, up to 5 gait frames >= 0.5 s apart).
Score = 0.35 side-on + 0.25 sharpness + 0.25 size + 0.15 confidence (weights from the team's `frame_extraction.py`).

**Habit trends** (`trends.py`): rolling 24 h windows, today against the previous 7 days. Rest flag: share >= baseline + 0.15 and >= 1.25x,
>= 6 sightings a day for >= 3 baseline days. Eating flag: group chewing minutes <= 60% of a baseline of >= 30 min. Gait flag: last three
scores never fall and rise by >= 1.

**Down for hours** (`suspects.lying_streak`): lying/sitting at every sighting back from the newest, >= 4 h and >= 3 sightings, newest within 3 h.

**Check this cow first** (`suspects.score_cow/rank/lines`): score = 0.5 x min(streak h / 6, 1) + 0.2 rest flag + 0.15 gait + 0.15 existing alert;
a cow is named if score >= 0.35 and ahead of the next by >= 0.15, otherwise "could not tell" with the most inactive.

## 5. API (summary)
| Group | Routes |
|---|---|
| Cows | `POST/GET /api/cows`, `GET /api/cows/{id}`, `/trends`, `/report?lang=`, `POST /resolve`, `DELETE` (admin) |
| Checks | `POST /api/analyze`, `/api/audio`, `/api/posture` |
| Devices | `POST /api/ingest` (device key), `GET /api/ingest/recent` |
| Assistant | `POST /api/ask`, `GET /api/kb`, `POST/DELETE /api/admin/kb` (admin) |
| System | `GET /api/alerts`, `/feeding`, `/sounds`, `/status`, `/health`, `POST /api/warmup`, `/api/alerts/{id}/resolve` |
| Demo (admin) | `POST /api/demo/seed`, `/history`, `/reset` |

## 6. Testing strategy
| Level | What | Where |
|---|---|---|
| Unit (110) | Every domain rule, rate limiter, tracing, store, matching, messages in 3 languages, report facts, kb chunking and search, ingest sniffing and frame sampling | `tests/unit` |
| API (25) | Access control, cows, vet documents, habit alerts, demo refresh and reset, rate limit, error mapping; no models needed | `tests/api` |
| Pipeline (17) | Real models in-process: skin results, face recognition, sound alerts with "check first", Pi route and frame agent; skipped without `serving/models` | `tests/api/test_pipeline_with_models.py` |
Run: `cd router && python -m pytest` (CI runs unit and API tests on every push).

## 7. Extending
New alert kind: add its template, short label and fact in `services/messages.py`, a rule in `domain/`, a check in `services/alerts.py`.
New model: add a task in `serving/`, call it through `infra/inference.py`. New route: schema in `api/schemas.py`, use-case in `services/`, thin route in `api/routes/`.
