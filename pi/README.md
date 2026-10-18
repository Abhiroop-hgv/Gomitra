# GoMitra Raspberry Pi uploader

The Pi only captures and uploads. All AI runs on Google Cloud. One address takes everything: `POST /api/ingest`.
The cloud router looks at each file and decides where it goes:

| What the Pi sends | Where the router sends it |
|---|---|
| Photo (JPEG/PNG) | skin screening + cow-face models, then alert rules. If exactly one registered cow is recognised, a walking/resting check (pose model + Gemini) runs at most every 10 minutes for that cow. |
| Short video (MP4) | 5 frames are taken, then the same as a photo. |
| Sound clip (WAV) | distress and eating-sound models, then alert rules. |

## The frame agent in the cloud
A single photo can be blurred, dark, or have the cow cut off. Short clips work better: the router's frame agent (`router/agent.py`,
its checks ported from the team's `frame_extraction.py`) reads the frames, drops the blurred, dark and duplicate ones, finds the
cow and her face, and then decides:
- clear face -> cow-face model (who is it?);
- cow clearly visible -> skin screening model and alert rules;
- cow side-on, fully visible, not blocked by another cow, big enough -> pose model and the walking check (best 5 frames);
- nothing usable -> nothing is sent to a model.
Run the Pi with `--video-every 60 --photo-every 0` to send a 5-second clip each minute. The agent's decisions are listed under
"What the frame agent decided" on the app's "How it works" screen.

## Set up on the Pi
```bash
sudo apt update && sudo apt install -y python3-requests alsa-utils     # camera tools (rpicam-still) come with Raspberry Pi OS
# optional USB camera fallback: sudo apt install -y python3-opencv
python3 gomitra_pi.py --url https://gomitra-337344659283.asia-south1.run.app --key YOUR_DEVICE_KEY --camera "North field camera"
```
Defaults: a photo every 60 s, a 10 s sound clip every 120 s. Change with `--photo-every`, `--sound-every`, `--sound-seconds`.
If the network drops, files wait in a spool folder and are sent later.

## Try it without a camera
```bash
python3 gomitra_pi.py --url ... --key ... --send cow.jpg     # prints what the router did with it
python3 gomitra_pi.py --url ... --key ... --send clip.wav
```

## Demo without a live camera: replay recorded footage
```bash
python3 gomitra_pi.py --url ... --key ... --replay cows.mp4 --replay-step 5 --replay-gap 4     # a frame every 5 s of video, one upload every 4 s
python3 gomitra_pi.py --url ... --key ... --replay ./photos --loop                              # or a folder of photos, repeated
```
It needs OpenCV for video (`sudo apt install python3-opencv`). Say clearly that this is recorded footage: the uploader, the router,
the models on Google Cloud and the alerts after the upload are the same as with a live camera.

## Run at boot (systemd)
Copy `gomitra-pi.service` to `/etc/systemd/system/`, put your values in it, then
`sudo systemctl enable --now gomitra-pi`. Logs: `journalctl -u gomitra-pi -f`.

## Notes
- The device key is separate from the admin key. Keep it on the Pi only (not in the repository).
- A walking check can take up to 2 minutes the first time after the pose model has been idle; the script waits.
- Cow recognition needs the cow to be registered with clear face photos and to face the camera; otherwise the frame is checked but not attached to a cow.
