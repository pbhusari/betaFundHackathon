"""
Z.AI scenario expansion agent.
Uses the Anthropic-compatible Z.AI API to expand a short prompt into a structured
edge-case scenario for aerial footage generation.
"""
import json
import logging
import os
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

ZAI_BASE_URL = "https://api.z.ai/api/anthropic"
DEFAULT_MODEL = "claude-3-5-haiku-20241022"  # maps to glm-4.5-air on Z.AI

SYSTEM_PROMPT = """You are an expert in aerial drone photography, computer vision dataset curation,
and edge-case scenario generation for autonomous systems.

Given a short description of an aerial scenario, expand it into a structured JSON object
with the following keys:
- lighting: describe the lighting conditions (e.g. "harsh backlight from low sun angle, 12% haze")
- weather: atmospheric weather description (e.g. "blowing dust, 30 mph crosswind")
- terrain: ground-level terrain details (e.g. "arid scrubland, rocky outcrops, sand dunes")
- time_of_day: exact time and sun position (e.g. "golden hour, ~17:30 local, sun at 8° elevation")
- atmospheric_effects: particulates, fog, rain, smoke, etc. (e.g. "PM2.5 dust suspended at 50-200m AGL")
- camera_artifacts: lens flare, motion blur, sensor noise, overexposure zones, etc.
- seedance_prompt: a single detailed English prompt string optimized for the Seedance video generation
  model. This should be 2-4 sentences, cinematic, technical, and describe the visual style,
  camera motion, and environmental conditions vividly. Start with "Aerial drone footage,".
  CRITICAL REQUIREMENTS for the seedance_prompt:
  - Describe a drone slowly orbiting in a wide circle at constant altitude, smooth circular pan, camera locked toward scene center
  - Real-time speed only — absolutely NO timelapse, NO hyperlapse, NO fast motion
  - ZERO cuts, ZERO scene changes, ZERO transitions — one single continuous uninterrupted shot
  - Use words like "slow", "gentle", "steady", "continuous", "uncut", "real-time" explicitly in the prompt

Respond ONLY with valid JSON matching this exact schema. No markdown fences, no extra text."""

USER_TEMPLATE = "Expand this aerial edge-case scenario: {short_prompt}"


class ZAIAgent:
    def __init__(self, api_key: str, base_url: str = ZAI_BASE_URL, model: str = DEFAULT_MODEL):
        self.model = model
        self.client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url)

    async def expand_scenario(self, short_prompt: str) -> dict:
        """
        Expand a short scenario prompt into a structured dict with keys:
        lighting, weather, terrain, time_of_day, atmospheric_effects,
        camera_artifacts, seedance_prompt.
        """
        logger.info("Expanding scenario with Z.AI: %s", short_prompt[:80])

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": USER_TEMPLATE.format(short_prompt=short_prompt)}],
        )

        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        try:
            scenario = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("Z.AI returned invalid JSON: %s", raw[:500])
            raise ValueError(f"Z.AI returned non-JSON response: {exc}") from exc

        required_keys = {
            "lighting", "weather", "terrain", "time_of_day",
            "atmospheric_effects", "camera_artifacts", "seedance_prompt",
        }
        missing = required_keys - set(scenario.keys())
        if missing:
            logger.warning("Z.AI response missing keys: %s — filling with defaults", missing)
            for key in missing:
                scenario[key] = "unspecified"

        return scenario

    async def expand_scenario_variants(self, short_prompt: str, n: int = 3) -> list[dict]:
        """
        Generate n independent scenario expansions for the same prompt.
        All requests fire concurrently.
        """
        import asyncio

        tasks = [self.expand_scenario(short_prompt) for _ in range(n)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        scenarios = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Variant %d expansion failed: %s", i, result)
                scenarios.append(_fallback_scenario(short_prompt, variant=i))
            else:
                scenarios.append(result)
        return scenarios


def _fallback_scenario(short_prompt: str, variant: int = 0) -> dict:
    suffixes = ["(dawn variant)", "(dusk variant)", "(midday variant)"]
    suffix = suffixes[variant % len(suffixes)]
    return {
        "lighting": "natural ambient light",
        "weather": "clear sky",
        "terrain": "mixed terrain",
        "time_of_day": "daytime",
        "atmospheric_effects": "none",
        "camera_artifacts": "none",
        "seedance_prompt": (
            f"Aerial drone footage, {short_prompt} {suffix}. "
            "Cinematic wide-angle shot, steady gimbal, photorealistic detail."
        ),
    }


def get_agent_from_env() -> ZAIAgent:
    api_key = os.getenv("ZAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("ZAI_API_KEY env var not set — copy .env.example to .env and fill in keys")
    return ZAIAgent(api_key=api_key)
