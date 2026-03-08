import json
import logging
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from vidasync_multiagents_ia.observability import record_external_request

OPEN_FOOD_FACTS_BASE_URL = "https://world.openfoodfacts.org"
OPEN_FOOD_FACTS_SEARCH_PATH = "/cgi/search.pl"


class OpenFoodFactsClientError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class OpenFoodFactsClient:
    def __init__(self, timeout_seconds: float = 20.0) -> None:
        self._timeout_seconds = timeout_seconds
        self._logger = logging.getLogger(__name__)

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
        started = perf_counter()
        self._logger.info(
            "open_food_facts.http.request",
            extra={
                "client": "open_food_facts",
                "operation": "search_products",
                "url": url,
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
                    },
                )
                record_external_request(
                    client="open_food_facts",
                    operation="search_products",
                    status=str(getattr(response, "status", 200)),
                    duration_ms=duration_ms,
                )
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise OpenFoodFactsClientError("Resposta invalida do Open Food Facts.", status_code=502) from exc
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
                },
            )
            record_external_request(
                client="open_food_facts",
                operation="search_products",
                status=str(exc.code),
                duration_ms=duration_ms,
            )
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
                },
            )
            record_external_request(
                client="open_food_facts",
                operation="search_products",
                status="network_error",
                duration_ms=duration_ms,
            )
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
                },
            )
            record_external_request(
                client="open_food_facts",
                operation="search_products",
                status="timeout",
                duration_ms=duration_ms,
            )
            raise OpenFoodFactsClientError("Open Food Facts request timeout while requesting search.") from exc
