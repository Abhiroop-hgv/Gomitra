# GoMitra: try it in 5 minutes

**Open:** https://gomitra-337344659283.asia-south1.run.app (best on a phone, in Chrome). Tap **Sign in**; any number works, it is a demo screen.
Pick English, हिंदी or తెలుగు at the top. Everything below works in all three.

## The 5-minute path
1. **Herd screen.** Red cows need attention. Open **Gauri** or **Nandini**: a message in your language, three steps to follow, and a **Call vet** button. Tap **Vet report** for a note you can send to a vet.
2. **Open Tulasi.** She is flagged for resting much more than her own usual week. Chewing for the group is also far below usual. (This uses a simulated week of data; the rules are real.)
3. **Test lab, Photo.** Pick a sample (healthy, lumpy skin, mouth-and-foot disease), choose a cow, tap **Check now**. Or upload your own cow photo.
4. **Test lab, Walk and rest.** Pick a sample or upload a walking video, tap **Check now**. About 25 seconds; the first check after a long quiet time can take up to 2 minutes while the pose model wakes up.
5. **Test lab, Sound.** Pick the loud call or calm call sample.
6. **Ask GoMitra.** Type or tap the mic (Chrome) and ask in any of the three languages, for example "How does lumpy skin disease spread?". Answers come only from the vet notes, with the source named. Ask something unrelated: it says it does not know and points to a vet.

More detailed cases with expected results: `TEST_CASES.md`. How it is built on Google Cloud: `ARCHITECTURE.md`.

## How to see that it is real
- Every result in the Test lab, Ask GoMitra and the Vet report has a **Behind this result** line. Open it to see which Google Cloud service did each step (Vertex AI endpoint, Gemini on Vertex AI, Vertex AI embeddings, Cloud Run, Firestore) and how long that step really took. The times are measured on that request.
- Upload **your own** cow photo, sound clip or walking video. The models give different numbers every time, and a blurry photo is refused.
- **How it works** (bottom of the herd screen) shows the live setup and the latest uploads from the camera device.

## What is real and what is simulated
| Real, running on Google Cloud | Simulated or sample, and labelled as such |
|---|---|
| Skin, cow-face, pose and sound models on Vertex AI and Cloud Run | The week of habit history for Tulasi, Kamala, Lakshmi and Nandini (resting, chewing, walking scores), loaded so the trends can be shown |
| Gemini 2.5 Flash: alerts, answers, walking score, vet report | The 6 demo cows (names, ear tags) |
| Vet-note search with Vertex AI embeddings, in Telugu, Hindi and English | The vet notes are short starter notes, not published veterinary documents |
| Firestore: cows, alerts, history | There is no live CCTV: the Raspberry Pi uploader is shown by replaying recorded footage through the same upload route |
| The upload route used by the Raspberry Pi (`/api/ingest`) and its routing | |

## What to know
- These are screening hints, not diagnoses. The vet notes in the demo are short starter notes, not published veterinary documents.
- Skin screening is 95.9% accurate on 614 clear held-out photos; it has not been tested on camera footage. The sound models are unvalidated (7 of 10 on our team's clips).
- The Raspberry Pi camera uploader is not part of this demo; photos and clips are uploaded by hand.
- If a button says "Too many requests", wait a minute; each visitor address has a per-minute limit to protect the demo's cost.
