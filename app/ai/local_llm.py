"""
Local LLM interface using Ollama + Qwen2.5.
Zero API costs — runs entirely on your machine.
"""
import json
import httpx
from typing import Dict, List, Optional
from datetime import datetime


class LocalLLM:
    """Interface to local Ollama server running Qwen2.5."""
    
    def __init__(self, model: str = "qwen2.5:3b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self.api_url = f"{base_url}/api/generate"
        self.chat_url = f"{base_url}/api/chat"
        self._available = False
        self._check_connection()
    
    def _check_connection(self):
        """Check if Ollama is running and model is available."""
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
    
    @property
    def available(self) -> bool:
        return self._available
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 temperature: float = 0.3, max_tokens: int = 2048) -> str:
        """Generate text from the local model."""
        if not self._available:
            return ""
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens
                }
            }
            r = httpx.post(self.chat_url, json=payload, timeout=120)
            if r.status_code == 200:
                return r.json()["message"]["content"]
            else:
                print(f"Ollama error: {r.status_code} {r.text[:200]}")
                return ""
        except Exception as e:
            print(f"Ollama request failed: {e}")
            return ""
    
    def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[Dict]:
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
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LocalLLM()
    return _llm_instance