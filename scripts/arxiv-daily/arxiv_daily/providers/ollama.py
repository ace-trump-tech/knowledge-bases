"""Local ollama HTTP client.

By design this is best-effort: ``arxiv-daily`` may run without a local model
(e.g. inside GitHub Actions). When ollama is unavailable, callers should fall
back to a stub response and emit a clear log line.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from ..exceptions import ProviderError

LOGGER = logging.getLogger(__name__)

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_TIMEOUT = 120.0


class OllamaUnavailable(ProviderError):
    def __init__(self, message: str = "ollama not reachable") -> None:
        super().__init__("ollama", message)


@dataclass(frozen=True)
class OllamaResponse:
    model: str
    text: str
    total_duration_ns: int
    prompt_tokens: int
    completion_tokens: int


class OllamaClient:
    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        model: str = "qwen2.5:14b",
        timeout: float = DEFAULT_TIMEOUT,
        temperature: float = 0.2,
        max_retries: int = 1,
    ) -> None:
        import requests

        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "arxiv-daily/0.1"})

    # -- public -----------------------------------------------------------

    def is_available(self) -> bool:
        import requests

        try:
            resp = self._session.get(f"{self.host}/api/tags", timeout=2.0)
        except requests.RequestException:
            return False
        return resp.status_code == 200

    def generate(self, prompt: str, system: Optional[str] = None) -> OllamaResponse:
        """Send a generate request; raise OllamaUnavailable on connectivity issues."""
        import requests

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        if system:
            payload["system"] = system

        attempt = 0
        while True:
            try:
                resp = self._session.post(
                    f"{self.host}/api/generate", json=payload, timeout=self.timeout
                )
            except requests.RequestException as exc:
                if attempt >= self.max_retries:
                    raise OllamaUnavailable(f"network: {exc}") from exc
                attempt += 1
                time.sleep(2)
                continue

            if resp.status_code == 404 and "model" in resp.text.lower():
                raise OllamaUnavailable(
                    f"model '{self.model}' not pulled; run: ollama pull {self.model}"
                )
            if resp.status_code != 200:
                raise ProviderError(
                    "ollama",
                    f"unexpected status {resp.status_code}: {resp.text[:200]}",
                    status=resp.status_code,
                )

            js = resp.json()
            return OllamaResponse(
                model=self.model,
                text=js.get("response", ""),
                total_duration_ns=js.get("total_duration") or 0,
                prompt_tokens=js.get("prompt_eval_count") or 0,
                completion_tokens=js.get("eval_count") or 0,
            )


__all__ = ["OllamaClient", "OllamaResponse", "OllamaUnavailable"]