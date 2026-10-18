# GoMitra: test cases for the jury

App: https://gomitra-337344659283.asia-south1.run.app (open on a phone or at phone width). Tap **Sign in** (no password needed in the demo).
Switch language with **EN / हिं / తె** at the top. Everything below works in all three.

Open **Test lab** from the herd screen. It has three tabs: Photo, Sound, and Walk and rest. There are six sample photos, two sample sounds and three sample walking photos, and you can upload your own.

| # | What to do | What you should see |
|---|---|---|
| 1 | Test lab, Photo: pick a **Healthy cow** sample, choose a cow (for example Rani), tap **Check now** | "Normal" bar near 100%. No alert. The cow stays "Healthy". |
| 2 | Pick a **Lumpy skin** sample, choose Gauri, Check now | "Lumpy skin" bar about 98%. A red alert in the chosen language with 3 numbered steps (separate the cow, call the vet, report) and the source note it came from. Back on the herd screen Gauri is red. |
| 3 | Pick a **Mouth and foot disease** sample, choose Nandini, Check now | "Foot-and-mouth" bar near 100%. Alert says to separate the cow, not move animals, call the vet and the animal husbandry office. |
| 4 | Upload a very small or blurry photo | "The photo is not clear enough." No alert is created. |
| 5 | Herd screen: open a red cow, tap **Mark as checked** | The alert clears. |
| 6 | Add cow: add 4 photos and an ear tag number, tap **Register cow** | "Cow added" with how many of the 4 photos contained a cow face. The cow appears in the herd. (Face matching needs clear front-facing photos.) |
| 7 | Ask GoMitra: tap a suggested question, or type "How does lumpy skin disease spread?" | A short answer in the selected language, built only from the vet notes, with the source named. |
| 8 | Ask GoMitra in Telugu or Hindi, or tap the mic and speak | Same answer in that language. (Voice input and read-aloud use the browser, so they work best in Chrome.) |
| 9 | Ask something not in the notes, for example "What is the price of milk today?" | It says it does not know and points to a vet. It does not make up an answer. |
| 10 | Test lab, Sound: pick **Loud call (distress example)**, Check now | "Possible distress call heard", with a note that sound models are not yet validated. |
| 11 | Sound: pick **Calm call** | No distress call, and a chewing result. You can also upload your own clip. |
| 12 | Test lab, Walk and rest: pick **Mild limp (photo)**, choose Nandini, Check now. Takes about 25 seconds (the first run after a long idle can take about a minute while the pose model starts) | An image with body points drawn on the cow, a walking score (about 2 of 5, "slightly uneven"), the posture (standing), and a note that it was judged from one photo. Open Nandini: the Walking and Resting rows are filled in. |
| 13 | Walk and rest: upload a short side-view walking video (5 frames are taken from it) | A walking score from 1 to 5 and the posture. A score of 3 or more raises a "limping" alert in the chosen language. If the video is blurry or the cow is cut off, it says no score instead of guessing. |
| 14 | Herd screen: look at the **Sounds today** card after running a sound sample | Group chewing time and meals, and the time of the last distress call. Cow screens show the same group figure on the Eating row, marked "group". |
| 15 | "How it works" at the bottom of the herd screen | Live status: where the models run (Cloud Run or Vertex AI), the Gemini model, number of cows and vet documents. |
| 16 | Herd screen: open **Tulasi** (red, "Lying for hours") | High-severity banner in the chosen language: she has been lying for hours without standing, and group chewing is also far below usual, with 3 steps and the source note. The Resting row says about "Resting 75% of the day (usual 39%)". |
| 16b | Test lab, Sound: pick **Loud call (distress example)**, Check now. Then look at the herd screen's **Sounds today** card | The alert and the card end with "Please check Tulasi first: lying for about 6 hours without standing; resting 75% of the day (usual 39%)", in the chosen language. If no cow stood out, it would say it could not tell which cow and list the most inactive. This is inference from the cameras, not proof of who made the sound. |
| 17 | Open **Kamala** or **Lakshmi** | Resting row says about 42-50% against a similar usual figure, marked OK. No alert: the app only alerts on a clear rise over her own week. |
| 18 | Herd screen: look at the **Sounds today** card | A red line "Group chewing is about 54% below usual", and the same on every cow's Eating row. Chewing is per camera group, not per cow. |
| 19 | Open **Nandini**: Walking row | "Walking score rising: 1 → 1 → 1 → 2 → 2" (marked Check). |
| 20 | Open a red cow (for example Tulasi), tap **Vet report**; switch language with EN / हिं / తె | A one-minute handover note for the vet in the chosen language: who the cow is, what the camera saw with numbers and dates, and what is not known (fever, appetite, milk, treatment). Buttons to send on WhatsApp or copy the text. It never states a diagnosis. |

| 21 | "How it works" screen: look at **Recent uploads from cameras** | The latest uploads sent by the camera device (or the team's Pi simulator), each with what it was and which models it went through, for example "Sound clip: loud distress-like call" with "sound models". The uploader itself needs a private device key, so the jury sees these results rather than sending uploads. Open "What the frame agent decided" on an entry: it lists how many frames were read, which were dropped (blurred, dark, duplicate, cow cut off, another cow in the way) and which model each kept frame went to. |

Cases 16 to 19 use a **simulated week** of habit data loaded for the demo (`POST /api/demo/history`), because we have no real week of farm video yet. The rules are real; the history is made up. It must be reloaded shortly before the demo, because "today" is always the last 24 hours.

## What each result is based on
- **Resting and eating trends:** each walking/resting check on a registered cow saves a standing/sitting/lying sighting. The app compares the share of sightings spent resting in the last 24 hours with the same cow's previous 7 days, and alerts only when it is at least 15 points and 1.25 times higher (and there are at least 6 sightings per day for 3 or more days). Chewing minutes for the camera group are compared the same way and alert at 60% or less of the usual. Thresholds are starting points, not tuned on farm data.
- **Lumpy skin / foot-and-mouth:** EfficientNet-B0, three classes (normal, lumpy, foot-and-mouth). Held-out accuracy 95.9% on 614 clear photos. It has **not** been tested on real camera (CCTV) footage.
- **Cow recognition:** cow-face detector plus DINOv2-small embeddings, matched at cosine similarity 0.69. Tuned on close-up photos, not on field cameras.
- **Walking and rest:** a pretrained pose model (DeepLabCut SuperAnimal-Quadruped) finds 17 body points; simple geometry rules say standing, sitting or lying; Gemini scores the gait 1 to 5 on the Sprecher scale from the pictures and the body points. Our teammate tested it on lame cows. We have not measured its accuracy here, a single photo cannot show a full stride, and the sample photo scores as a mild limp (2 of 5), not as an alert.
- **Sound:** two open models from the CattlePlus project. On the 10 labelled clips from our team the distress model got **7 of 10** right, and its scores are always 0 or 1, so it never shows doubt. Treat sound results as a hint only.
- **Messages and advice:** Gemini on Vertex AI, using retrieved passages of the vet notes. The notes in the demo are short starter notes written for this project, not published veterinary documents. A vet must review them before real use.

## Not in the demo
Real week-long farm data for the trends, bloat detection, matching a sound to one cow out of three, retraining from farmer feedback, and a test on real Raspberry Pi hardware (the uploader script is written and was run from a laptop; the "recognise one cow, then walking check" path was tested with stand-ins, not yet with a real registered cow in a real camera frame).

All alerts are screening hints, not diagnoses.
