"""
SkyAugment — Aerial Edge-Case Generator
FastAPI backend
"""
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Optional

import aiofiles
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SEEDANCE_API_KEYS_RAW = os.getenv("SEEDANCE_API_KEYS", "")
SEEDANCE_API_KEYS = [k.strip() for k in SEEDANCE_API_KEYS_RAW.split(",") if k.strip()]

ZAI_API_KEY = os.getenv("ZAI_API_KEY", "")
USE_CACHE = os.getenv("USE_CACHE", "true").lower() != "false"

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "demo_assets" / "cached_outputs"
FRONTEND_DIR = BASE_DIR / "frontend"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

NUM_VARIANTS = 3

PRE_BAKED_SCENARIOS = [
    "dust storm at low sun angle over desert highway",
    "heavy rain at night over urban intersection",
    "dense fog at sunrise over coastal wetlands",
    "wildfire smoke layer at dusk over forest",
    "snowstorm whiteout over mountain ridge",
]

# ---------------------------------------------------------------------------
# Lazy-initialised API clients
# ---------------------------------------------------------------------------
_seedance_client = None
_zai_agent = None


def get_seedance_client():
    global _seedance_client
    if _seedance_client is None:
        from seedance_client import SeedanceClient, DEFAULT_MODEL as SEEDANCE_DEFAULT_MODEL
        _seedance_client = SeedanceClient(api_keys=SEEDANCE_API_KEYS)
    return _seedance_client


def get_zai_agent():
    global _zai_agent
    if _zai_agent is None:
        from zai_agent import ZAIAgent
        _zai_agent = ZAIAgent(api_key=ZAI_API_KEY)
    return _zai_agent


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------
def _cache_key(prompt: str, image_name: Optional[str]) -> str:
    raw = f"{prompt}|{image_name or 'noimage'}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def _read_cache(key: str) -> Optional[dict]:
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    async with aiofiles.open(path, "r") as f:
        return json.loads(await f.read())


async def _write_cache(key: str, data: dict) -> None:
    path = CACHE_DIR / f"{key}.json"
    async with aiofiles.open(path, "w") as f:
        await f.write(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# Video download helper — persists Seedance URLs locally before they expire
# ---------------------------------------------------------------------------
VIDEO_CACHE_DIR = BASE_DIR / "demo_assets" / "videos"
VIDEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)


async def _localise_video(video_url: Optional[str]) -> Optional[str]:
    """Download a remote video URL to local storage and return the local /videos/ path."""
    if not video_url or video_url.startswith("/"):
        return video_url
    import hashlib as _hl
    fname = _hl.md5(video_url.encode()).hexdigest()[:12] + ".mp4"
    local = VIDEO_CACHE_DIR / fname
    if not local.exists():
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(video_url)
                resp.raise_for_status()
                tmp = local.with_suffix(".tmp.mp4")
                async with aiofiles.open(tmp, "wb") as f:
                    await f.write(resp.content)
            # Move moov atom to front for browser streaming (faststart)
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", str(tmp), "-c:v", "copy", "-movflags", "faststart", str(local),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            tmp.unlink(missing_ok=True)
            if not local.exists():  # ffmpeg failed, fall back to raw file
                tmp.rename(local)
            logger.info("Saved video locally: %s", fname)
        except Exception as exc:
            logger.warning("Could not localise video %s: %s", video_url, exc)
            return video_url
    return f"/videos/{fname}"


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="SkyAugment", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount frontend and local video cache as static files
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

VIDEO_DIR = BASE_DIR / "demo_assets" / "videos"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/videos", StaticFiles(directory=str(VIDEO_DIR)), name="videos")


@app.get("/")
async def serve_frontend():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"error": "frontend/index.html not found"}, status_code=404)


# ---------------------------------------------------------------------------
# API routes — all under /api
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    return {"status": "ok", "cache_enabled": USE_CACHE}


@app.get("/api/videos")
async def list_videos():
    """Return all cached videos across all prompts."""
    items = []
    for jf in sorted(CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(jf.read_text())
            for v in data.get("variants", []):
                if v.get("video_url"):
                    items.append({
                        "video_url": v["video_url"],
                        "prompt": v.get("prompt", ""),
                        "scenario": v.get("scenario", {}),
                        "cache_key": data.get("cache_key", ""),
                    })
        except Exception:
            pass
    return {"videos": items}


@app.get("/api/scenarios")
async def list_scenarios():
    return {"scenarios": PRE_BAKED_SCENARIOS}


@app.post("/api/generate")
async def generate(
    prompt: str = Form(...),
    image: Optional[UploadFile] = File(None),
):
    """
    Accept a text prompt and an optional image upload.
    Returns JSON: {variants: [{video_url, prompt, scenario}]}
    """
    if not prompt.strip():
        raise HTTPException(status_code=422, detail="prompt must not be empty")

    image_name: Optional[str] = image.filename if image else None
    cache_key = _cache_key(prompt, image_name)

    # --- Cache check ---
    if USE_CACHE:
        cached = await _read_cache(cache_key)
        if cached:
            logger.info("Cache HIT for key %s", cache_key)
            return JSONResponse(cached)

    logger.info("Cache MISS — generating %d variants for: %s", NUM_VARIANTS, prompt[:80])

    # --- Read uploaded image (if any) ---
    image_bytes: Optional[bytes] = None
    image_data_url: Optional[str] = None
    if image:
        image_bytes = await image.read()
        import base64
        suffix = (image.filename or "").rsplit(".", 1)[-1].lower()
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(suffix, "image/jpeg")
        b64 = base64.b64encode(image_bytes).decode()
        image_data_url = f"data:{mime};base64,{b64}"

    # --- Expand scenarios concurrently with Z.AI ---
    zai = get_zai_agent()
    try:
        scenarios = await zai.expand_scenario_variants(prompt, n=NUM_VARIANTS)
    except Exception as exc:
        logger.error("Z.AI expansion failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Scenario expansion failed: {exc}")

    # --- Generate videos concurrently with Seedance ---
    seedance = get_seedance_client()

    async def _generate_one(scenario: dict, idx: int) -> dict:
        seedance_prompt = scenario.get("seedance_prompt", prompt)
        seedance_prompt += (
            " CRITICAL: absolutely zero cuts, zero scene changes, zero transitions, zero jump cuts, zero dissolves, zero new camera angles."
            " This must be ONE single uninterrupted continuous shot from the very first frame to the very last frame."
            " Slow gentle drone orbit at constant altitude, smooth circular pan, camera always locked toward the scene center."
            " Real-time speed only — strictly NO timelapse, NO hyperlapse, NO fast motion, NO speed ramp."
            " Calm, slow, cinematic. Any cut or speed change means the video is rejected."
        )
        try:
            if image_data_url:
                video_url = await seedance.generate(image_data_url, seedance_prompt)
            else:
                # No image — use text-only prompt as best effort
                # Seedance requires an image; send a placeholder note and skip video call
                # In a real deployment you'd have a default aerial reference image
                video_url = None
                logger.warning("No image provided for variant %d — skipping video generation", idx)
            return {"video_url": video_url, "prompt": seedance_prompt, "scenario": scenario}
        except Exception as exc:
            logger.error("Video generation failed for variant %d: %s", idx, exc)
            return {"video_url": None, "prompt": seedance_prompt, "scenario": scenario, "error": str(exc)}

    tasks = [_generate_one(s, i) for i, s in enumerate(scenarios)]
    variants = list(await asyncio.gather(*tasks))

    # --- Download videos locally so signed URLs don't expire ---
    for v in variants:
        v["video_url"] = await _localise_video(v.get("video_url"))

    result = {"variants": variants, "cache_key": cache_key}

    # --- Save to cache ---
    if USE_CACHE:
        await _write_cache(cache_key, result)

    return JSONResponse(result)
