# Still → Motion

A small web app that turns an uploaded photo + a text prompt into an
8-second MP4 clip, using a free-tier-friendly AI image-to-video model.

```
img2vid/
├── app.py              # Flask backend (Python) — calls the AI model, builds the 8s clip
├── requirements.txt    # Python dependencies
├── .env.example        # Copy to .env and add your API token
└── static/
    ├── index.html       # Page markup
    ├── style.css         # Styling
    └── script.js          # Frontend logic (JavaScript) — upload, drag/drop, calls the API
```

## How it works

1. You upload an image and write a prompt describing the motion
   ("slow zoom in, clouds drifting, gentle wind").
2. The Python backend sends both to an image-to-video model hosted on
   [Replicate](https://replicate.com).
3. Because most free/open models only offer a couple of fixed clip
   lengths, the backend runs the raw output through `ffmpeg` to loop
   or trim it to **exactly 8 seconds** before sending it back to the browser.

## Why Replicate

It's the most practical **free** starting point for this: new accounts
get a small amount of free trial credit, there's no self-hosted GPU to
manage, and the model is swappable via one environment variable. There
is no permanently-free hosted image-to-video API as of 2026 — every
provider (Runway, Kling, Luma, Pika, Stability) is either paid or
capped free-trial credit. If you'd rather run everything at zero
ongoing cost, see "Running fully free" below.

## Setup

**1. Install dependencies**

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**2. Install ffmpeg** (used to force the clip to 8 seconds)

```bash
# macOS
brew install ffmpeg
# Ubuntu/Debian
sudo apt install ffmpeg
# Windows: https://ffmpeg.org/download.html
```

**3. Add your API token**

```bash
cp .env.example .env
# then edit .env and paste your token from
# https://replicate.com/account/api-tokens
```

Load it before running the server:

```bash
export $(grep -v '^#' .env | xargs)   # macOS/Linux
```

**4. Run it**

```bash
python app.py
```

Open `http://localhost:5000` in your browser.

## Running fully free (no API costs at all)

Instead of calling Replicate, you can self-host the open-source
Stable Video Diffusion model with `diffusers` on your own GPU (or a
free Colab GPU). Swap out `call_video_model()` in `app.py` for a local
`diffusers` pipeline call — the rest of the app (upload UI, 8-second
normalization, download) stays the same. This needs a GPU with at
least ~16GB VRAM and is slower than a hosted API, but has zero
per-generation cost.

## Swapping the AI model

Change `REPLICATE_MODEL` in `.env` to any other image-to-video model
slug on Replicate (e.g. a Kling or Luma community version), as long as
it accepts `input_image` and `prompt` inputs. Check the model's page
on Replicate for its exact input schema — some use `image` instead of
`input_image`, in which case update the key in `call_video_model()`
in `app.py` to match.

## Notes

- Generation can take anywhere from 30 seconds to a few minutes
  depending on model load — this demo does a single blocking request
  rather than a job queue, which is fine for personal use but should
  be swapped for a background task queue (e.g. Celery/RQ) before
  putting this in front of real traffic.
- Uploaded images are deleted from the server right after generation;
  generated clips are kept in `outputs/` — add your own cleanup job if
  you're running this long-term.
