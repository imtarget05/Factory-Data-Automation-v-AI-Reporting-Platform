"""
Local LLM interface — Ollama (native /api/chat) or an OpenAI-compatible LAN
endpoint (LM Studio on the M1 Pro / llm-gateway at /v1/chat/completions).

Zero API costs — runs entirely on your machine / LAN.

    LLM_PROVIDER=ollama    -> native Ollama protocol (default, back-compat)
    LLM_PROVIDER=lmstudio  -> OpenAI-compatible /v1/chat/completions
                              (LMSTUDIO_BASE_URL, LMSTUDIO_MODEL)
"""

import json
import os
from typing import Optional

import httpx

DEFAULT_LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://192.168.1.8:1234/v1")
DEFAULT_LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "qwen2.5-vl-3b-instruct")


class LocalLLM:
    """Interface to a local model: Ollama native or OpenAI-compatible (LM Studio)."""

    def __init__(
        self,
        model: str = "qwen2.5:3b",
        base_url: str = "http://localhost:11434",
        provider: Optional[str] = None,
    ):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "ollama")).strip().lower()
        self.model = model
        self.base_url = base_url
        self.api_url = f"{base_url}/api/generate"
        self.chat_url = f"{base_url}/api/chat"
        self._available = False
        self._check_connection()

    # -- availability probes ------------------------------------------------
    def _check_connection(self):
        """Check if the provider is running and the model is available."""
        if self.provider in ("lmstudio", "local_openai", "lms"):
            return self._check_lmstudio()
        return self._check_ollama()

    def _check_ollama(self):
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=3)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                if any(self.model in m for m in models):
                    self._available = True
                    print(f"✅ Local LLM ready: {self.model}")
                else:
                    print(f"⚠️  Model {self.model} not found. Pull it: ollama pull {self.model}")
            else:
                print(f"⚠️  Ollama server not available at {self.base_url}")
        except Exception as e:
            print(f"⚠️  Cannot connect to Ollama: {e}")
            print("   Start it: brew services start ollama")

    def _check_lmstudio(self):
        try:
            r = httpx.get(f"{self.base_url}/models", timeout=3)
            if r.status_code == 200:
                models = [m.get("id", "") for m in r.json().get("data", [])]
                if any(self.model in m for m in models):
                    self._available = True
                    print(f"✅ Local LLM ready ({self.provider}): {self.model}")
                else:
                    print(f"⚠️  Model {self.model} not served at {self.base_url}. Available: {models}")
            else:
                print(f"⚠️  LM Studio not available at {self.base_url}")
        except Exception as e:
            print(f"⚠️  Cannot connect to {self.base_url}: {e}")

    @property
    def available(self) -> bool:
        return self._available

    # -- generation ---------------------------------------------------------
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        """Generate text from the local model."""
        if not self._available:
            return ""

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        if self.provider in ("lmstudio", "local_openai", "lms"):
            return self._generate_lmstudio(messages, temperature, max_tokens)
        return self._generate_ollama(messages, temperature, max_tokens)

    def _generate_ollama(self, messages: list, temperature: float, max_tokens: int) -> str:
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            }
            r = httpx.post(self.chat_url, json=payload, timeout=120)
            if r.status_code == 200:
                return r.json()["message"]["content"]
            print(f"Ollama error: {r.status_code} {r.text[:200]}")
            return ""
        except Exception as e:
            print(f"Ollama request failed: {e}")
            return ""

    def _generate_lmstudio(self, messages: list, temperature: float, max_tokens: int) -> str:
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            }
            r = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json", "X-Project": "Factory-Data-Automation"},
                timeout=180,
            )
            if r.status_code == 200:
                choices = r.json().get("choices") or []
                return (choices[0].get("message", {}).get("content", "") if choices else "") or ""
            print(f"LM Studio error: {r.status_code} {r.text[:200]}")
            return ""
        except Exception as e:
            print(f"LM Studio request failed: {e}")
            return ""

    def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[dict]:
        """Generate and parse JSON response."""
        full_prompt = prompt + "\n\nRespond ONLY with valid JSON. No markdown, no code blocks."
        response = self.generate(full_prompt, system_prompt, temperature=0.1)

        if not response:
            return None

        # Extract JSON from response
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
            return json.loads(response)
        except json.JSONDecodeError:
            print(f"Failed to parse JSON from LLM response (len={len(response)})")
            return None


# Singleton
_llm_instance: Optional[LocalLLM] = None


def get_llm() -> LocalLLM:
    """Return the process-wide LocalLLM (Ollama native or LM Studio OpenAI-compat)."""
    global _llm_instance
    if _llm_instance is None:
        from app.utils.config import (
            LLM_PROVIDER,
            LMSTUDIO_BASE_URL,
            LMSTUDIO_MODEL,
            OLLAMA_BASE_URL,
            OLLAMA_MODEL,
        )

        if LLM_PROVIDER.strip().lower() in ("lmstudio", "local_openai", "lms"):
            _llm_instance = LocalLLM(
                model=LMSTUDIO_MODEL,
                base_url=LMSTUDIO_BASE_URL.rstrip("/"),
                provider="lmstudio",
            )
        else:
            _llm_instance = LocalLLM(
                model=OLLAMA_MODEL,
                base_url=OLLAMA_BASE_URL,
                provider="ollama",
            )
    return _llm_instance
