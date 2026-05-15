"""Multi-provider AI backend with fallback chain.

Supports: Gemini, Groq, OpenRouter, Mistral, Together AI,
GitHub Models, any OpenAI-compatible endpoint, and local Ollama.

Each provider is tried in priority order. If one fails, the next
is attempted until one succeeds or all are exhausted.
"""

import base64
import json
import logging
import subprocess
import shutil
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from .utils import strip_code_fences, strip_indentation

logger = logging.getLogger("codemaker.providers")

_MAX_RETRIES = 2
_RETRY_DELAY = 1.5  # seconds (base delay)
_RATE_LIMIT_DELAY = 5.0  # seconds (longer delay for 429s)
_TIMEOUT = 60  # seconds


# ──────────────────────────────────────────────────────────────────
# Provider configs
# ──────────────────────────────────────────────────────────────────

# Well-known base URLs for provider types
_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "mistral": "https://api.mistral.ai/v1",
    "together": "https://api.together.xyz/v1",
    "github": "https://models.inference.ai.azure.com",
}


@dataclass
class ProviderConfig:
    """Configuration for a single API provider."""

    name: str  # e.g. "provider_1", "local"
    provider_type: str  # gemini, groq, openrouter, mistral, together, github, openai, ollama
    api_key: str = ""
    model: str = ""
    base_url: str = ""

    # Two-stage local pipeline (ollama only)
    vision_model: str = ""   # e.g. qwen2.5vl:7b
    code_model: str = ""     # e.g. qwen2.5-coder:7b
    vision_prompt: str = ""  # Prompt for the vision extraction step

    @property
    def is_pipeline(self) -> bool:
        """Check if this is a two-stage vision→code pipeline."""
        return bool(self.vision_model and self.code_model)

    @property
    def is_configured(self) -> bool:
        """Check if this provider has minimum required config."""
        if self.provider_type == "ollama":
            return bool(self.model) or self.is_pipeline
        if self.provider_type == "gemini":
            return bool(self.api_key and self.model)
        # OpenAI-compatible providers
        return bool(self.api_key and self.model)

    @property
    def effective_base_url(self) -> str:
        """Get the base URL, using well-known defaults if not set."""
        if self.base_url:
            return self.base_url
        return _BASE_URLS.get(self.provider_type, "")


# ──────────────────────────────────────────────────────────────────
# Provider implementations
# ──────────────────────────────────────────────────────────────────


def _call_gemini(
    cfg: ProviderConfig, image_bytes: bytes, prompt: str
) -> str:
    """Call Google Gemini API using google-genai SDK."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=cfg.api_key)
    response = client.models.generate_content(
        model=cfg.model,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            prompt,
        ],
    )
    text = response.text
    if not text:
        raise RuntimeError("Gemini returned empty response")
    return text


def _call_openai_compatible(
    cfg: ProviderConfig, image_bytes: bytes, prompt: str
) -> str:
    """Call any OpenAI-compatible vision API (Groq, OpenRouter, Mistral, etc.)."""
    base_url = cfg.effective_base_url
    if not base_url:
        raise RuntimeError(
            f"No base_url for provider type '{cfg.provider_type}'. "
            "Set BASE_URL in the provider config."
        )

    b64_image = base64.b64encode(image_bytes).decode("ascii")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.api_key}",
    }

    # OpenRouter wants additional headers
    if cfg.provider_type == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/codemaker"
        headers["X-Title"] = "CodeMaker"

    payload = {
        "model": cfg.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_image}",
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
        "max_tokens": 4096,
        "temperature": 0.2,
    }

    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
        )

    if resp.status_code != 200:
        error_body = resp.text[:500]
        raise RuntimeError(
            f"{cfg.provider_type} API error {resp.status_code}: {error_body}"
        )

    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    if not text:
        raise RuntimeError(f"{cfg.provider_type} returned empty response")
    return text


def _call_ollama(
    cfg: ProviderConfig, image_bytes: bytes, prompt: str
) -> str:
    """Call local Ollama API with vision support.

    If the provider has both vision_model and code_model configured,
    delegates to the two-stage pipeline instead.
    """
    if cfg.is_pipeline:
        return _call_ollama_pipeline(cfg, image_bytes, prompt)

    base_url = cfg.base_url or "http://localhost:11434"

    _check_ollama_running(base_url)
    _ensure_ollama_model(cfg.model, base_url)

    b64_image = base64.b64encode(image_bytes).decode("ascii")

    payload = {
        "model": cfg.model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [b64_image],
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 4096,
        },
    }

    with httpx.Client(timeout=120) as client:
        resp = client.post(f"{base_url}/api/chat", json=payload)

    if resp.status_code != 200:
        raise RuntimeError(f"Ollama error {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    text = data.get("message", {}).get("content", "")
    if not text:
        raise RuntimeError("Ollama returned empty response")
    return text


def _check_ollama_running(base_url: str) -> None:
    """Verify the Ollama server is reachable, auto-starting it if needed."""
    try:
        with httpx.Client(timeout=5) as client:
            client.get(f"{base_url}/api/version")
        return  # Already running
    except (httpx.ConnectError, httpx.TimeoutException):
        pass  # Not running — try to start it

    # Attempt to auto-start Ollama
    ollama_path = shutil.which("ollama")
    if not ollama_path:
        raise RuntimeError(
            "Ollama is not installed. Install it from: https://ollama.com"
        )

    logger.info("Ollama not running — starting automatically...")
    try:
        subprocess.Popen(
            [ollama_path, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Detach from parent process
        )
    except OSError as ex:
        raise RuntimeError(f"Failed to start Ollama: {ex}")

    # Wait for Ollama to become ready (up to 15 seconds)
    for i in range(30):
        time.sleep(0.5)
        try:
            with httpx.Client(timeout=2) as client:
                client.get(f"{base_url}/api/version")
            logger.info("Ollama started successfully (took ~%.1fs)", (i + 1) * 0.5)
            return
        except (httpx.ConnectError, httpx.TimeoutException):
            continue

    raise RuntimeError(
        "Ollama was started but failed to become ready within 15 seconds. "
        "Check `ollama serve` manually for errors."
    )


def _unload_ollama_model(model: str, base_url: str) -> None:
    """Unload a model from Ollama VRAM by setting keep_alive to 0."""
    try:
        with httpx.Client(timeout=30) as client:
            client.post(
                f"{base_url}/api/generate",
                json={"model": model, "prompt": "", "keep_alive": 0},
            )
        logger.info("Unloaded model '%s' from VRAM", model)
    except Exception as ex:
        logger.warning("Failed to unload model '%s': %s", model, ex)


def _call_ollama_pipeline(
    cfg: ProviderConfig, image_bytes: bytes, prompt: str
) -> str:
    """Two-stage local pipeline: vision model extracts question, code model generates code.

    Stage 1: Load vision model → extract coding question from screenshot → unload
    Stage 2: Load code model → generate code from extracted question → return

    This allows using the full VRAM for each model separately, resulting in
    better quality from larger, specialized models.
    """
    base_url = cfg.base_url or "http://localhost:11434"

    _check_ollama_running(base_url)

    # ── Stage 1: Vision extraction ──
    logger.info("[pipeline] Stage 1: Loading vision model '%s'...", cfg.vision_model)
    _ensure_ollama_model(cfg.vision_model, base_url)

    vision_prompt = cfg.vision_prompt or (
        "Extract only the coding problem or question from this screenshot. "
        "Ignore all UI elements, navigation bars, buttons, ads, and unrelated text. "
        "Output ONLY the problem statement, input/output format, constraints, "
        "and examples. Do not solve it."
    )

    b64_image = base64.b64encode(image_bytes).decode("ascii")

    vision_payload = {
        "model": cfg.vision_model,
        "messages": [
            {
                "role": "user",
                "content": vision_prompt,
                "images": [b64_image],
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,  # Low temp for accurate extraction
            "num_predict": 2048,
        },
    }

    with httpx.Client(timeout=180) as client:
        resp = client.post(f"{base_url}/api/chat", json=vision_payload)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Ollama vision error {resp.status_code}: {resp.text[:500]}"
        )

    extracted_question = resp.json().get("message", {}).get("content", "")
    if not extracted_question:
        raise RuntimeError("Vision model returned empty extraction")

    logger.info(
        "[pipeline] Extracted question: %d chars", len(extracted_question)
    )
    logger.debug("[pipeline] Question preview: %s...", extracted_question[:200])

    # ── Unload vision model to free VRAM ──
    logger.info("[pipeline] Unloading vision model...")
    _unload_ollama_model(cfg.vision_model, base_url)

    # ── Stage 2: Code generation ──
    logger.info("[pipeline] Stage 2: Loading code model '%s'...", cfg.code_model)
    _ensure_ollama_model(cfg.code_model, base_url)

    code_payload = {
        "model": cfg.code_model,
        "messages": [
            {
                "role": "user",
                "content": f"{prompt}\n\nHere is the problem:\n\n{extracted_question}",
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 4096,
        },
    }

    with httpx.Client(timeout=300) as client:  # Code gen can be slow on 7B
        resp = client.post(f"{base_url}/api/chat", json=code_payload)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Ollama code error {resp.status_code}: {resp.text[:500]}"
        )

    code_text = resp.json().get("message", {}).get("content", "")
    if not code_text:
        raise RuntimeError("Code model returned empty response")

    logger.info("[pipeline] Code generated: %d chars", len(code_text))

    # Unload code model too (free VRAM for desktop usage)
    _unload_ollama_model(cfg.code_model, base_url)

    return code_text


def _ensure_ollama_model(model: str, base_url: str) -> None:
    """Check if an Ollama model is downloaded, auto-pull if not."""
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{base_url}/api/tags")
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            installed = {m.get("name", "") for m in models}
            # Check both exact name and name:latest
            if model in installed or f"{model}:latest" in installed:
                logger.debug("Ollama model '%s' is available", model)
                return

            # Also check by stripping :latest suffix
            model_base = model.split(":")[0]
            for m in installed:
                if m.split(":")[0] == model_base:
                    logger.debug(
                        "Ollama model '%s' found as '%s'", model, m
                    )
                    return
    except Exception as ex:
        logger.warning("Could not check Ollama models: %s", ex)

    # Model not found — auto-pull
    logger.info(
        "Ollama model '%s' not found locally. Pulling (this may take a while)...",
        model,
    )

    # Try API pull first
    try:
        with httpx.Client(timeout=600) as client:
            resp = client.post(
                f"{base_url}/api/pull",
                json={"name": model, "stream": False},
                timeout=600,
            )
        if resp.status_code == 200:
            logger.info("Successfully pulled model '%s'", model)
            return
    except Exception:
        pass

    # Fallback to CLI
    if shutil.which("ollama"):
        logger.info("Pulling via ollama CLI...")
        result = subprocess.run(
            ["ollama", "pull", model],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            logger.info("Successfully pulled model '%s'", model)
            return
        raise RuntimeError(
            f"Failed to pull Ollama model '{model}': {result.stderr}"
        )

    raise RuntimeError(
        f"Ollama model '{model}' not found and could not auto-pull. "
        f"Run manually: ollama pull {model}"
    )


# ──────────────────────────────────────────────────────────────────
# Provider dispatch
# ──────────────────────────────────────────────────────────────────

_DISPATCH = {
    "gemini": _call_gemini,
    "groq": _call_openai_compatible,
    "openrouter": _call_openai_compatible,
    "mistral": _call_openai_compatible,
    "together": _call_openai_compatible,
    "github": _call_openai_compatible,
    "openai": _call_openai_compatible,
    "ollama": _call_ollama,
}


def _call_provider(
    cfg: ProviderConfig, image_bytes: bytes, prompt: str
) -> str:
    """Call a single provider with retry logic."""
    func = _DISPATCH.get(cfg.provider_type)
    if func is None:
        raise RuntimeError(f"Unknown provider type: {cfg.provider_type}")

    last_error: Optional[Exception] = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            logger.info(
                "[%s] Sending screenshot (%s), attempt %d/%d",
                cfg.name, cfg.model, attempt + 1, _MAX_RETRIES + 1,
            )
            raw_text = func(cfg, image_bytes, prompt)
            code = strip_indentation(strip_code_fences(raw_text))
            logger.info(
                "[%s] Response: %d chars of code", cfg.name, len(code)
            )
            logger.debug("Code preview: %s...", code[:100])
            return code

        except Exception as ex:
            last_error = ex
            logger.warning(
                "[%s] Error (attempt %d): %s", cfg.name, attempt + 1, ex
            )
            if attempt < _MAX_RETRIES:
                # Use longer delay for rate limits (429)
                is_rate_limit = "429" in str(ex) or "rate" in str(ex).lower()
                delay = _RATE_LIMIT_DELAY if is_rate_limit else _RETRY_DELAY
                delay *= (attempt + 1)
                logger.debug("Retrying in %.1fs...", delay)
                time.sleep(delay)

    raise RuntimeError(
        f"[{cfg.name}] Failed after {_MAX_RETRIES + 1} attempts: {last_error}"
    )


# ──────────────────────────────────────────────────────────────────
# Public API — process with fallback chain
# ──────────────────────────────────────────────────────────────────


def process_screenshot(
    image_bytes: bytes,
    system_prompt: str,
    providers: list[ProviderConfig],
) -> str:
    """Process a screenshot through the provider fallback chain.

    Tries each configured provider in priority order. If one fails,
    the next is attempted.

    Args:
        image_bytes: PNG screenshot bytes.
        system_prompt: Prompt sent with the image.
        providers: Ordered list of provider configs (highest priority first).

    Returns:
        Cleaned code string.

    Raises:
        RuntimeError: If all providers fail.
    """
    if not providers:
        raise RuntimeError(
            "No AI providers configured. Set up at least one provider in .env"
        )

    active = [p for p in providers if p.is_configured]
    if not active:
        raise RuntimeError(
            "No providers are properly configured. "
            "Check API keys and model names in .env"
        )

    errors = []
    for cfg in active:
        try:
            return _call_provider(cfg, image_bytes, system_prompt)
        except RuntimeError as ex:
            errors.append(f"{cfg.name} ({cfg.provider_type}): {ex}")
            logger.warning(
                "Provider %s failed, trying next fallback...", cfg.name
            )
            continue

    raise RuntimeError(
        "All AI providers failed:\n" + "\n".join(f"  • {e}" for e in errors)
    )
