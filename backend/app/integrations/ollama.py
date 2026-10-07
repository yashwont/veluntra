"""A thin HTTP client for a local Ollama server (https://ollama.com).

Shared by the chat-model adapter (`app.llm.ollama`) and the embedding adapter
(`app.embeddings.ollama`). It turns every way the call can go wrong into an
`OllamaError` with a message that says what to do about it. Request and response
bodies are never logged: they hold the user's personal data.
"""

from typing import Any

import httpx


class OllamaError(Exception):
    """Ollama could not be reached or did not answer usefully. `str(exc)` says why and
    what to try; it never contains request content."""


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport  # tests inject a mock transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url, timeout=httpx.Timeout(self.timeout), transport=self._transport
        )

    async def post(self, path: str, payload: dict[str, Any], *, model: str) -> dict[str, Any]:
        return await self._request("POST", path, model=model, json=payload)

    async def get(self, path: str) -> dict[str, Any]:
        return await self._request("GET", path, model=None)

    async def _request(
        self, method: str, path: str, *, model: str | None, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            async with self._client() as client:
                response = await client.request(method, path, json=json)
        except httpx.ConnectError as exc:
            raise OllamaError(
                f"Cannot reach Ollama at {self.base_url}. Is it running? "
                "(start the Ollama app, or run `ollama serve`)"
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaError(
                f"Ollama did not answer within {self.timeout:g}s. A local model on a slow "
                "computer can take a while: try a smaller model or raise OLLAMA_TIMEOUT_SECONDS."
            ) from exc
        except httpx.HTTPError as exc:
            raise OllamaError(f"Could not talk to Ollama ({type(exc).__name__}).") from exc

        if response.status_code == 404 and model:
            raise OllamaError(f"Ollama does not have the model '{model}'. Install it with: ollama pull {model}")
        if not response.is_success:
            raise OllamaError(f"Ollama returned HTTP {response.status_code}.")
        try:
            data = response.json()
        except ValueError as exc:
            raise OllamaError("Ollama returned something that is not JSON.") from exc
        if not isinstance(data, dict):
            raise OllamaError("Ollama returned an unexpected response.")
        return data
