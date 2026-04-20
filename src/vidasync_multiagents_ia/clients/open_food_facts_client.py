import json
import logging
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from vidasync_multiagents_ia.core.cache import TTLCache
from vidasync_multiagents_ia.core.circuit_breaker import CircuitBreaker, CircuitOpenError
from vidasync_multiagents_ia.observability import record_external_request
from vidasync_multiagents_ia.observability.payload_preview import preview_text, sanitize_url

OPEN_FOOD_FACTS_BASE_URL = "https://world.openfoodfacts.org"
OPEN_FOOD_FACTS_SEARCH_PATH = "/cgi/search.pl"


class OpenFoodFactsClientError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class OpenFoodFactsClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
        *,
        log_payloads: bool = True,
        log_max_chars: int = 4000,
        cache_ttl_seconds: float = 0.0,
        cache_max_entries: int = 256,
        circuit_failure_threshold: int = 5,
        circuit_recovery_seconds: float = 30.0,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._logger = logging.getLogger(__name__)
        self._log_payloads = log_payloads
        self._log_max_chars = max(256, log_max_chars)
        self._cache: TTLCache[str, dict] = TTLCache(
            ttl_seconds=cache_ttl_seconds,
            max_entries=cache_max_entries,
        )
        self._breaker = CircuitBreaker(
            name="open_food_facts",
            failure_threshold=circuit_failure_threshold,
            recovery_seconds=circuit_recovery_seconds,
        )

    def search_products(
        self,
        *,
        query: str,
        page: int = 1,
        page_size: int = 10,
    ) -> dict:
        params = {
            "search_terms": query,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page": page,
            "page_size": page_size,
            "fields": "code,product_name,brands,image_url,nutriments",
        }
        url = f"{OPEN_FOOD_FACTS_BASE_URL}{OPEN_FOOD_FACTS_SEARCH_PATH}?{urlencode(params)}"
        cached = self._cache.get(url)
        if cached is not None:
            record_external_request(
                client="open_food_facts",
                operation="search_products",
                status="cache_hit",
                duration_ms=0.0,
            )
            return cached
        try:
            self._breaker.before_call()
        except CircuitOpenError as exc:
            record_external_request(
                client="open_food_facts",
                operation="search_products",
                status="circuit_open",
                duration_ms=0.0,
            )
            raise OpenFoodFactsClientError(
                "Open Food Facts circuit open while requesting search."
            ) from exc
        started = perf_counter()
        self._logger.info(
            "open_food_facts.http.request",
            extra={
                "client": "open_food_facts",
                "operation": "search_products",
                "url": sanitize_url(url),
                "query": query,
                "page": page,
                "page_size": page_size,
                "timeout_seconds": self._timeout_seconds,
            },
        )

        request = Request(
            url=url,
            headers={
                "User-Agent": "VidaSync-Multiagents-IA/1.0",
            },
        )

        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="ignore")
                duration_ms = (perf_counter() - started) * 1000.0
                self._logger.info(
                    "open_food_facts.http.response",
                    extra={
                        "client": "open_food_facts",
                        "operation": "search_products",
                        "status_code": getattr(response, "status", 200),
                        "duration_ms": round(duration_ms, 4),
                        "response_size_bytes": len(raw.encode("utf-8")),
                        "response_preview": self._preview(raw),
                    },
                )
                record_external_request(
                    client="open_food_facts",
                    operation="search_products",
                    status=str(getattr(response, "status", 200)),
                    duration_ms=duration_ms,
                )
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError as exc:
                    self._breaker.record_failure()
                    raise OpenFoodFactsClientError("Resposta invalida do Open Food Facts.", status_code=502) from exc
                self._cache.set(url, payload)
                self._breaker.record_success()
                return payload
        except HTTPError as exc:
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.warning(
                "open_food_facts.http.error",
                extra={
                    "client": "open_food_facts",
                    "operation": "search_products",
                    "status_code": exc.code,
                    "duration_ms": round(duration_ms, 4),
                    "error_type": "HTTPError",
                    "url": sanitize_url(url),
                },
            )
            record_external_request(
                client="open_food_facts",
                operation="search_products",
                status=str(exc.code),
                duration_ms=duration_ms,
            )
            self._breaker.record_failure()
            raise OpenFoodFactsClientError(
                f"Open Food Facts HTTP error while requesting search: {exc.code}",
                status_code=exc.code,
            ) from exc
        except URLError as exc:
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.warning(
                "open_food_facts.http.error",
                extra={
                    "client": "open_food_facts",
                    "operation": "search_products",
                    "status_code": "network_error",
                    "duration_ms": round(duration_ms, 4),
                    "error_type": "URLError",
                    "url": sanitize_url(url),
                },
            )
            record_external_request(
                client="open_food_facts",
                operation="search_products",
                status="network_error",
                duration_ms=duration_ms,
            )
            self._breaker.record_failure()
            raise OpenFoodFactsClientError("Open Food Facts network error while requesting search.") from exc
        except TimeoutError as exc:
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.warning(
                "open_food_facts.http.error",
                extra={
                    "client": "open_food_facts",
                    "operation": "search_products",
                    "status_code": "timeout",
                    "duration_ms": round(duration_ms, 4),
                    "error_type": "TimeoutError",
                    "url": sanitize_url(url),
                },
            )
            record_external_request(
                client="open_food_facts",
                operation="search_products",
                status="timeout",
                duration_ms=duration_ms,
            )
            self._breaker.record_failure()
            raise OpenFoodFactsClientError("Open Food Facts request timeout while requesting search.") from exc

    def _preview(self, raw: str) -> str | None:
        if not self._log_payloads:
            return None
        return preview_text(raw, max_chars=self._log_max_chars)
