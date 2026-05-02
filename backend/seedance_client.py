"""
Seedance 2.0 (BytePlus Ark) async client with round-robin API key rotation.
"""
import asyncio
import base64
import itertools
import logging
import os
import time
from pathlib import Path
from typing import List, Optional, Union

import httpx

logger = logging.getLogger(__name__)

SEEDANCE_BASE_URL = "https://ark.ap-southeast.bytepluses.com/api/v3"
DEFAULT_MODEL = "dreamina-seedance-2-0-fast-260128"
MODEL_STANDARD = "dreamina-seedance-2-0-260128"
POLL_INTERVAL_SECONDS = 5
MAX_POLL_ATTEMPTS = 60  # 5 minutes max
SUBMIT_ENDPOINT = "/contents/generations/tasks"
POLL_ENDPOINT = "/contents/generations/tasks/{task_id}"


class SeedanceClient:
    def __init__(self, api_keys: List[str], base_url: str = SEEDANCE_BASE_URL):
        if not api_keys:
            raise ValueError("At least one API key is required")
        self.api_keys = api_keys
        self.base_url = base_url.rstrip("/")
        self._key_cycle = itertools.cycle(api_keys)
        self._lock = asyncio.Lock()

    async def _next_key(self) -> str:
        async with self._lock:
            return next(self._key_cycle)

    def _auth_headers(self, api_key: str) -> dict:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _encode_image_to_data_url(image_path: str) -> str:
        """Read a local file and return a base64 data URL."""
        path = Path(image_path)
        suffix = path.suffix.lower().lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(
            suffix, "image/jpeg"
        )
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return f"data:{mime};base64,{b64}"

    @staticmethod
    def _resolve_image_url(image: str) -> str:
        """If image is a local path, encode it; otherwise return as-is."""
        if image.startswith("http://") or image.startswith("https://") or image.startswith("data:"):
            return image
        return SeedanceClient._encode_image_to_data_url(image)

    async def submit_image_to_video(
        self,
        image_url_or_base64: str,
        prompt: str,
        model: str = DEFAULT_MODEL,
    ) -> tuple[str, str]:
        """
        Submit an image-to-video generation task.
        Returns (task_id, api_key_used).
        """
        api_key = await self._next_key()
        url = self._resolve_image_url(image_url_or_base64)

        payload = {
            "model": model,
            "content": [
                {"type": "image_url", "image_url": {"url": url}},
                {"type": "text", "text": prompt},
            ],
            "generate_audio": False,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}{SUBMIT_ENDPOINT}",
                json=payload,
                headers=self._auth_headers(api_key),
            )
            resp.raise_for_status()
            data = resp.json()

        task_id = data.get("id") or data.get("task_id")
        if not task_id:
            raise RuntimeError(f"No task_id in response: {data}")
        logger.info("Submitted image-to-video task %s", task_id)
        return task_id, api_key

    async def submit_reference_to_video(
        self,
        image_paths_or_urls: List[str],
        prompt: str,
        model: str = DEFAULT_MODEL,
    ) -> tuple[str, str]:
        """
        Submit a reference-to-video (multi-image) task.
        Returns (task_id, api_key_used).
        """
        api_key = await self._next_key()

        content = []
        for img in image_paths_or_urls:
            url = self._resolve_image_url(img)
            content.append({"type": "image_url", "image_url": {"url": url}})
        content.append({"type": "text", "text": prompt})

        payload = {"model": model, "content": content, "generate_audio": False}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}{SUBMIT_ENDPOINT}",
                json=payload,
                headers=self._auth_headers(api_key),
            )
            resp.raise_for_status()
            data = resp.json()

        task_id = data.get("id") or data.get("task_id")
        if not task_id:
            raise RuntimeError(f"No task_id in response: {data}")
        logger.info("Submitted reference-to-video task %s", task_id)
        return task_id, api_key

    async def poll_task(self, task_id: str, api_key: str) -> str:
        """
        Poll until the task completes (status == 'succeeded') or times out.
        Returns the video URL.
        Raises on failure or timeout.
        """
        attempt = 0
        delay = 10  # start with 10s — image-to-video never finishes in <10s

        while attempt < MAX_POLL_ATTEMPTS:
            await asyncio.sleep(delay)
            attempt += 1

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self.base_url}{POLL_ENDPOINT.format(task_id=task_id)}",
                    headers=self._auth_headers(api_key),
                )
            resp.raise_for_status()
            data = resp.json()

            status = (data.get("status") or "").lower()
            logger.info("Task %s status=%s (attempt %d)", task_id, status, attempt)

            if status in ("succeeded", "completed", "success"):
                video_url = (
                    (data.get("content") or {}).get("video_url")
                    or data.get("video_url")
                    or (data.get("output") or {}).get("video_url")
                )
                if not video_url:
                    raise RuntimeError(f"Task succeeded but no video URL found: {data}")
                return video_url

            if status in ("failed", "error", "cancelled"):
                error = data.get("error") or data.get("message") or status
                raise RuntimeError(f"Task {task_id} failed: {error}")

            # Exponential backoff capped at 30s
            delay = min(delay * 1.2, 30)

        raise TimeoutError(f"Task {task_id} did not complete within {MAX_POLL_ATTEMPTS * POLL_INTERVAL_SECONDS}s")

    async def generate(self, image_url: str, prompt: str, model: str = DEFAULT_MODEL) -> str:
        """
        End-to-end: submit image-to-video task, poll until done, return video URL.
        """
        task_id, api_key = await self.submit_image_to_video(image_url, prompt, model)
        video_url = await self.poll_task(task_id, api_key)
        return video_url

    async def generate_from_references(
        self, image_paths_or_urls: List[str], prompt: str, model: str = DEFAULT_MODEL
    ) -> str:
        """
        End-to-end multi-reference: submit + poll → video URL.
        """
        task_id, api_key = await self.submit_reference_to_video(image_paths_or_urls, prompt, model)
        video_url = await self.poll_task(task_id, api_key)
        return video_url


def get_client_from_env() -> SeedanceClient:
    raw = os.getenv("SEEDANCE_API_KEYS", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise RuntimeError("SEEDANCE_API_KEYS env var not set or empty")
    return SeedanceClient(api_keys=keys)
