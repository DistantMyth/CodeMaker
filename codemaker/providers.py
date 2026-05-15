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

from .utils import strip_code_fences, strip_c_comments, strip_indentation

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
    vision_model: str = ""       # e.g. minicpm-v
    code_model: str = ""         # e.g. qwen2.5-coder:7b (fast, fits in VRAM)
    quality_code_model: str = "" # e.g. qwen2.5-coder:14b (slow, GPU+CPU split)
    vision_prompt: str = ""      # Prompt for the vision extraction step

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
        "keep_alive": 0,  # Unload after inference to free RAM
        "options": {
            "temperature": 0.2,
            "num_predict": 4096,
            "num_ctx": 4096,     # Limit context to avoid huge KV cache allocation
        },
    }

    with httpx.Client(timeout=None) as client:
        resp = client.post(f"{base_url}/api/chat", json=payload)

    if resp.status_code != 200:
        raise RuntimeError(f"Ollama error {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    text = data.get("message", {}).get("content", "")
    if not text:
        raise RuntimeError("Ollama returned empty response")
    return text


def _check_ollama_running(base_url: str) -> None:
    """Verify the Ollama server is reachable, auto-starting it if needed.

    Prefers systemctl to avoid spawning a rogue ``ollama serve`` process
    that conflicts with the systemd unit (which causes a restart loop
    and "address already in use" errors).
    """
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

    # Prefer systemctl (avoids conflicting with systemd-managed service)
    started = False
    systemctl_path = shutil.which("systemctl")
    if systemctl_path:
        try:
            result = subprocess.run(
                [systemctl_path, "start", "ollama"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                logger.info("Started Ollama via systemctl")
                started = True
            else:
                logger.debug(
                    "systemctl start ollama failed (rc=%d): %s",
                    result.returncode, result.stderr.strip(),
                )
        except (OSError, subprocess.TimeoutExpired) as ex:
            logger.debug("systemctl start failed: %s", ex)

    # Fallback: direct ollama serve (only if systemctl didn't work)
    if not started:
        try:
            subprocess.Popen(
                [ollama_path, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # Detach from parent process
            )
            logger.info("Started Ollama via direct 'ollama serve'")
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


def _drop_filesystem_cache() -> None:
    """Try to drop Linux filesystem caches to reclaim buff/cache memory.

    Ollama's memory check counts 'available' memory (free + reclaimable),
    but filesystem cache from recent large downloads (model pulls) can
    make 'available' appear lower than it should be. Dropping caches
    forces the OS to reclaim that memory.

    Requires root privileges (which CodeMaker typically runs with).
    Silently ignored if not running as root.
    """
    try:
        import os
        # sync + drop pagecache only (1 = pagecache, 2 = dentries/inodes, 3 = both)
        os.sync()
        with open("/proc/sys/vm/drop_caches", "w") as f:
            f.write("1\n")
        logger.info("Dropped filesystem caches to reclaim memory")
    except (PermissionError, OSError) as ex:
        logger.debug("Could not drop caches (need root): %s", ex)


def _get_loaded_models(base_url: str) -> set[str]:
    """Query Ollama /api/ps to get the set of currently loaded model names."""
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{base_url}/api/ps")
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            return {m.get("name", "") for m in models if m.get("name")}
    except Exception as ex:
        logger.debug("Could not query loaded models: %s", ex)
    return set()


def _unload_ollama_model(model: str, base_url: str) -> None:
    """Unload a model from Ollama VRAM/RAM.

    First checks /api/ps to see if the model is actually loaded.
    If not loaded, skips entirely to avoid the load-then-unload paradox
    where Ollama loads the model into RAM just to process the keep_alive=0 request.
    After sending the unload, polls /api/ps until the model disappears.
    """
    # Check if model is actually loaded before trying to unload
    loaded = _get_loaded_models(base_url)
    model_loaded = any(
        model == m or model.split(":")[0] == m.split(":")[0]
        for m in loaded
    )
    if not model_loaded:
        logger.debug("Model '%s' not currently loaded, skipping unload", model)
        return

    try:
        with httpx.Client(timeout=30) as client:
            client.post(
                f"{base_url}/api/generate",
                json={"model": model, "prompt": "", "keep_alive": 0},
            )
        logger.info("Sent unload request for '%s'", model)
    except Exception as ex:
        logger.warning("Failed to send unload for '%s': %s", model, ex)
        return

    # Poll /api/ps until the model is actually gone (max ~10 seconds)
    for i in range(20):
        time.sleep(0.5)
        loaded = _get_loaded_models(base_url)
        still_loaded = any(
            model == m or model.split(":")[0] == m.split(":")[0]
            for m in loaded
        )
        if not still_loaded:
            logger.info("Confirmed model '%s' unloaded (took ~%.1fs)", model, (i + 1) * 0.5)
            return

    logger.warning("Model '%s' may still be loaded after 10s wait", model)


def _unload_all_loaded_models(base_url: str) -> None:
    """Unload ALL currently loaded Ollama models.

    Uses /api/ps to discover what's loaded, then unloads only those.
    This avoids the bug where blindly unloading a model that isn't loaded
    causes Ollama to load it first (consuming RAM).
    """
    loaded = _get_loaded_models(base_url)
    if not loaded:
        logger.debug("No models currently loaded in Ollama")
        return

    logger.info("Currently loaded models: %s", ", ".join(loaded))
    for model in loaded:
        _unload_ollama_model(model, base_url)


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

    # ── Ensure both models are downloaded upfront ──
    # Doing this before anything else ensures the user sees any necessary
    # download progress bars immediately, rather than waiting for Stage 1
    # to finish before finding out Stage 2 needs a download.
    logger.info("[pipeline] Checking model availability...")
    use_quality = bool(cfg.quality_code_model)
    active_code_model = cfg.quality_code_model if use_quality else cfg.code_model
    _ensure_ollama_model(cfg.vision_model, base_url)
    _ensure_ollama_model(active_code_model, base_url)

    # ── Pre-cleanup: unload any leftover models from previous runs ──
    # Uses /api/ps to only unload what's actually loaded — avoids the
    # load-to-unload paradox that was causing OOM errors.
    logger.info("[pipeline] Clearing VRAM/RAM before starting...")
    _unload_all_loaded_models(base_url)
    _drop_filesystem_cache()  # Reclaim buff/cache memory (especially after pulls)

    # ── Stage 1: Vision extraction ──
    logger.info("[pipeline] Stage 1: Loading vision model '%s'...", cfg.vision_model)

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
        "keep_alive": 0,  # Unload immediately after inference — critical for memory
        "options": {
            "temperature": 0.1,  # Low temp for accurate extraction
            "num_predict": 2048,
            "num_ctx": 2048,     # Small context — we only extract a problem statement
        },
    }

    with httpx.Client(timeout=None) as client:
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
    logger.info("[pipeline] ── Extracted Question ──\n%s", extracted_question)
    logger.info("[pipeline] ── End of Extracted Question ──")

    # ── Unload vision model to free VRAM ──
    logger.info("[pipeline] Unloading vision model...")
    _unload_ollama_model(cfg.vision_model, base_url)

    # ── Stage 2: Code generation ──
    # Choose between quality model (large, GPU+CPU split) and fast model (fits in VRAM)
    use_quality = bool(cfg.quality_code_model)
    active_code_model = cfg.quality_code_model if use_quality else cfg.code_model

    if use_quality:
        logger.info(
            "[pipeline] Stage 2: Loading QUALITY code model '%s' (GPU+CPU split, slower)...",
            active_code_model,
        )
        # Drop caches again — quality model needs every byte of RAM
        _drop_filesystem_cache()
    else:
        logger.info("[pipeline] Stage 2: Loading code model '%s'...", active_code_model)

    # Quality model gets larger context since it runs
    # partially on CPU (~5-10 tok/s vs ~20+ tok/s for the fast model)
    code_ctx = 8192 if use_quality else 4096

    code_payload = {
        "model": active_code_model,
        "messages": [
            {
                "role": "user",
                "content": f"{prompt}\n\nHere is the problem:\n\n{extracted_question}",
            }
        ],
        "stream": False,
        "keep_alive": 0,  # Unload immediately after inference — free RAM for desktop
        "options": {
            "temperature": 0.2,
            "num_predict": 4096,
            "num_ctx": code_ctx,
        },
    }

    with httpx.Client(timeout=None) as client:
        resp = client.post(f"{base_url}/api/chat", json=code_payload)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Ollama code error {resp.status_code}: {resp.text[:500]}"
        )

    code_text = resp.json().get("message", {}).get("content", "")
    if not code_text:
        raise RuntimeError("Code model returned empty response")

    logger.info("[pipeline] Code generated: %d chars (%s mode)", len(code_text),
                "quality" if use_quality else "fast")

    # Unload code model too (free VRAM+RAM for desktop usage)
    _unload_ollama_model(active_code_model, base_url)

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

            # If the user specified a base model without a tag (e.g. "minicpm-v"),
            # and it is installed with ANY tag, accept it. But DO NOT match
            # different tags if the user specifically requested one.
            if ":" not in model:
                for m in installed:
                    if m.split(":")[0] == model:
                        logger.debug(
                            "Ollama model '%s' found as '%s'", model, m
                        )
                        return
    except Exception as ex:
        logger.warning("Could not check Ollama models: %s", ex)

    # Model not found — auto-pull with progress
    logger.info(
        "Ollama model '%s' not found locally. Pulling (this may take a while)...",
        model,
    )

    # Use streaming API pull to show download progress
    try:
        with httpx.Client(timeout=600) as client:
            with client.stream(
                "POST",
                f"{base_url}/api/pull",
                json={"name": model, "stream": True},
                timeout=600,
            ) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(f"Pull failed: HTTP {resp.status_code}")

                last_pct = -1
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    status = data.get("status", "")
                    total = data.get("total", 0)
                    completed = data.get("completed", 0)

                    if total and total > 0:
                        pct = int(completed / total * 100)
                        # Log every 5% to avoid spam
                        if pct >= last_pct + 5:
                            last_pct = pct
                            total_gb = total / (1024 ** 3)
                            done_gb = completed / (1024 ** 3)
                            logger.info(
                                "  Pulling '%s': %d%% (%.1f / %.1f GB)",
                                model, pct, done_gb, total_gb,
                            )
                    elif status:
                        logger.info("  Pulling '%s': %s", model, status)

        logger.info("Successfully pulled model '%s'", model)
        return
    except RuntimeError:
        raise
    except Exception as ex:
        logger.warning("Streaming pull failed: %s — trying CLI...", ex)

    # Fallback to CLI (shows progress in subprocess output)
    if shutil.which("ollama"):
        logger.info("Pulling via ollama CLI...")
        # Use Popen to stream CLI output in real-time
        proc = subprocess.Popen(
            ["ollama", "pull", model],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in proc.stdout:
            line = line.strip()
            if line:
                logger.info("  ollama: %s", line)
        proc.wait()
        if proc.returncode == 0:
            logger.info("Successfully pulled model '%s'", model)
            return
        raise RuntimeError(
            f"Failed to pull Ollama model '{model}' (exit code {proc.returncode})"
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
            code = strip_c_comments(strip_indentation(strip_code_fences(raw_text)))
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


def cleanup_local_models(providers: list[ProviderConfig]) -> None:
    """Force-unload all Ollama models from VRAM.

    Called on reset combo or kill switch to free GPU memory immediately,
    even if the pipeline thread is still running.
    Uses /api/ps to only unload models that are actually loaded.
    """
    for cfg in providers:
        if cfg.provider_type != "ollama":
            continue

        base_url = cfg.base_url or "http://localhost:11434"

        # Check if Ollama is reachable (don't auto-start for cleanup)
        try:
            with httpx.Client(timeout=2) as client:
                client.get(f"{base_url}/api/version")
        except (httpx.ConnectError, httpx.TimeoutException):
            continue  # Ollama not running, nothing to clean up

        # Unload whatever is actually loaded (safe — won't load anything new)
        _unload_all_loaded_models(base_url)
