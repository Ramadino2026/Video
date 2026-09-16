"""
AI Image-to-Video Generator - Backend
--------------------------------------
Turns an uploaded image + a text prompt into an 8-second MP4 clip.

Pipeline:
  1. Receive image + prompt from the web page.
  2. Send both to an image-to-video model hosted on Replicate.
  3. Download whatever length clip the model returns.
  4. Use ffmpeg to force the final file to exactly 8 seconds
     (looping it if the model's native output is shorter, trimming
     it if longer) — this matters because almost no free/open
     image-to-video model accepts an arbitrary "8 seconds" input;
     most only offer a couple of fixed lengths (e.g. 4s or 5s).

Free tier: new Replicate accounts get a small amount of free trial
credit, which is enough to test this end-to-end without a paid plan.
Get a token at https://replicate.com/account/api-tokens

Requirements: pip install -r requirements.txt, and ffmpeg installed
and on PATH (e.g. `apt install ffmpeg` / `brew install ffmpeg`).
"""

import os
import subprocess
import tempfile
import uuid

import replicate
import requests
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CLIP_SECONDS = 8
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}

# Swap this for any other image-to-video model slug on Replicate.
# stable-video-diffusion is open-source and one of the cheapest/free-tier
# friendly options for prototyping.
REPLICATE_MODEL = os.environ.get(
    "REPLICATE_MODEL",
    "stability-ai/stable-video-diffusion-img2vid-xt",
)

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="")


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def call_video_model(image_path: str, prompt: str) -> str:
    """Send the image + prompt to Replicate, return a local path to the
    raw generated clip (whatever native length the model produces)."""
    token = os.environ.get("REPLICATE_API_TOKEN")
    client = replicate.Client(api_token=token)

    with open(image_path, "rb") as f:
        output = client.run(
            REPLICATE_MODEL,
            input={
                "input_image": f,
                "prompt": prompt,
            },
        )

    # `output` may be a single URL or a list of URLs depending on the
    # model version - normalize it either way.
    video_url = output[0] if isinstance(output, list) else output

    raw_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}.mp4")
    with requests.get(video_url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(raw_path, "wb") as out_f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                out_f.write(chunk)

    return raw_path


def normalize_to_clip_length(raw_path: str, seconds: int) -> str:
    """Guarantee the final file is exactly `seconds` long: loop the clip
    if it's shorter than that, trim it if it's longer. Requires ffmpeg."""
    final_path = os.path.join(OUTPUT_DIR, f"{uuid.uuid4()}.mp4")

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-stream_loop", "-1",   # loop the input indefinitely...
            "-i", raw_path,
            "-t", str(seconds),     # ...then cut it to exactly N seconds
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            final_path,
        ],
        check=True,
        capture_output=True,
    )
    return final_path


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/generate", methods=["POST"])
def generate():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    image = request.files["image"]
    prompt = request.form.get("prompt", "").strip()

    if image.filename == "" or not allowed_file(image.filename):
        return jsonify({"error": "Please upload a .png, .jpg or .webp image"}), 400
    if not prompt:
        return jsonify({"error": "Please write a prompt describing the motion"}), 400
    if "REPLICATE_API_TOKEN" not in os.environ:
        return jsonify({"error": "Server is missing REPLICATE_API_TOKEN. See .env.example"}), 500

    filename = secure_filename(image.filename)
    saved_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{filename}")
    image.save(saved_path)

    try:
        raw_video = call_video_model(saved_path, prompt)
        final_video = normalize_to_clip_length(raw_video, CLIP_SECONDS)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "ffmpeg failed", "details": e.stderr.decode()[:500]}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(saved_path):
            os.remove(saved_path)

    return jsonify({
        "video_url": f"/outputs/{os.path.basename(final_video)}",
        "duration": CLIP_SECONDS,
    })


@app.route("/outputs/<path:filename>")
def serve_output(filename):
    return send_from_directory(OUTPUT_DIR, filename)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
