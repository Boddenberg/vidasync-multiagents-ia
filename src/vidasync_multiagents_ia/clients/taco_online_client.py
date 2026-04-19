import logging
import re
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from vidasync_multiagents_ia.core import normalize_pt_text
from vidasync_multiagents_ia.core.cache import TTLCache
from vidasync_multiagents_ia.observability import record_external_request
from vidasync_multiagents_ia.observability.payload_preview import preview_text, sanitize_url
from vidasync_multiagents_ia.schemas import TacoOnlineFoodIndexItem, TacoOnlineRawFoodData

TACO_ONLINE_BASE_URL = "https://www.tabelatacoonline.com.br"
TACO_ONLINE_FOOD_PATH_PREFIX = "/tabela-nutricional/taco/"


class TacoOnlineClientError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TacoOnlineParsingError(RuntimeError):
    pass


class TacoOnlineClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
        *,
        log_payloads: bool = True,
        log_max_chars: int = 4000,
        cache_ttl_seconds: float = 0.0,
        cache_max_entries: int = 256,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._logger = logging.getLogger(__name__)
        self._cached_index: list[TacoOnlineFoodIndexItem] | None = None
        self._log_payloads = log_payloads
        self._log_max_chars = max(256, log_max_chars)
        self._http_cache: TTLCache[str, str] = TTLCache(
            ttl_seconds=cache_ttl_seconds,
            max_entries=cache_max_entries,
        )

    def fetch_html(self, page_url: str) -> str:
        cached = self._http_cache.get(page_url)
        if cached is not None:
            record_external_request(
                client="taco_online",
                operation="fetch_html",
                status="cache_hit",
                duration_ms=0.0,
            )
            return cached
        started = perf_counter()
        self._logger.info(
            "taco_online.http.request",
            extra={
                "client": "taco_online",
                "operation": "fetch_html",
                "url": sanitize_url(page_url),
                "timeout_seconds": self._timeout_seconds,
            },
        )
        request = Request(
            url=page_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
        )

        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                content = response.read()
                encoding = response.headers.get_content_charset() or "utf-8"
                decoded = content.decode(encoding, errors="ignore")
                duration_ms = (perf_counter() - started) * 1000.0
                self._logger.info(
                    "taco_online.http.response",
                    extra={
                        "client": "taco_online",
                        "operation": "fetch_html",
                        "url": sanitize_url(page_url),
                        "status_code": getattr(response, "status", 200),
                        "duration_ms": round(duration_ms, 4),
                        "response_size_bytes": len(content),
                        "response_preview": self._preview(decoded),
                    },
                )
                record_external_request(
                    client="taco_online",
                    operation="fetch_html",
                    status=str(getattr(response, "status", 200)),
                    duration_ms=duration_ms,
                )
                self._http_cache.set(page_url, decoded)
                return decoded
        except HTTPError as exc:
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.warning(
                "taco_online.http.error",
                extra={
                    "client": "taco_online",
                    "operation": "fetch_html",
                    "url": sanitize_url(page_url),
                    "status_code": exc.code,
                    "duration_ms": round(duration_ms, 4),
                    "error_type": "HTTPError",
                },
            )
            record_external_request(
                client="taco_online",
                operation="fetch_html",
                status=str(exc.code),
                duration_ms=duration_ms,
            )
            raise TacoOnlineClientError(
                f"TACO Online HTTP error while requesting '{page_url}': {exc.code}",
                status_code=exc.code,
            ) from exc
        except URLError as exc:
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.warning(
                "taco_online.http.error",
                extra={
                    "client": "taco_online",
                    "operation": "fetch_html",
                    "url": sanitize_url(page_url),
                    "status_code": "network_error",
                    "duration_ms": round(duration_ms, 4),
                    "error_type": "URLError",
                },
            )
            record_external_request(
                client="taco_online",
                operation="fetch_html",
                status="network_error",
                duration_ms=duration_ms,
            )
            raise TacoOnlineClientError(f"TACO Online network error while requesting '{page_url}'.") from exc
        except TimeoutError as exc:
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.warning(
                "taco_online.http.error",
                extra={
                    "client": "taco_online",
                    "operation": "fetch_html",
                    "url": sanitize_url(page_url),
                    "status_code": "timeout",
                    "duration_ms": round(duration_ms, 4),
                    "error_type": "TimeoutError",
                },
            )
            record_external_request(
                client="taco_online",
                operation="fetch_html",
                status="timeout",
                duration_ms=duration_ms,
            )
            raise TacoOnlineClientError(f"TACO Online request timeout while requesting '{page_url}'.") from exc

    def _preview(self, raw: str) -> str | None:
        if not self._log_payloads:
            return None
        return preview_text(raw, max_chars=self._log_max_chars)

    def extract_public_food_data(self, html: str, expected_slug: str | None) -> TacoOnlineRawFoodData:
        window = self._find_food_window(html=html, expected_slug=expected_slug)
        if not window:
            raise TacoOnlineParsingError("Food data block not found in public page.")

        return TacoOnlineRawFoodData(
            slug=self._extract_slug(window) or expected_slug,
            nome_alimento=self.extract_food_name(window),
            grupo_alimentar=self.extract_food_group(window),
            base_calculo=self.extract_base_amount(html=html, data_window=window),
            nutrientes=self.extract_public_nutrients(window),
        )

    def find_best_taco_slug(self, query: str) -> TacoOnlineFoodIndexItem | None:
        query_normalized = _normalize_text(query)
        if not query_normalized:
            return None

        items = [item for item in self._load_public_index() if item.tabela == "TACO"]
        if not items:
            return None

        query_tokens = [token for token in query_normalized.split(" ") if token]
        scored: list[tuple[int, int, TacoOnlineFoodIndexItem]] = []
        for index, item in enumerate(items):
            score = self._score_index_item(query_normalized=query_normalized, query_tokens=query_tokens, item=item)
            scored.append((score, -index, item))

        scored.sort(reverse=True)
        best_score, _, best_item = scored[0]
        if best_score <= 0:
            return None
        return best_item

    def extract_food_name(self, data_window: str) -> str | None:
        return self._extract_raw_value(data_window, "descricao")

    def extract_food_group(self, data_window: str) -> str | None:
        return self._extract_raw_value(data_window, "grupo")

    def extract_base_amount(self, html: str, data_window: str) -> str:
        serving_size = self._extract_raw_value(data_window, "servingSize")
        if not serving_size:
            serving_size = self._extract_raw_value(html, "servingSize")

        if not serving_size:
            return "100 gramas"

        normalized = serving_size.strip().lower().replace(" ", "")
        if normalized in {"100g", "100gramas", "100grama"}:
            return "100 gramas"
        return serving_size

    def extract_public_nutrients(self, data_window: str) -> dict[str, str | None]:
        key_map = {
            "energia_kcal": "energia_kcal",
            "energia_kj": "energia_kj",
            "carboidratos_g": "carboidrato_g",
            "proteina_g": "proteina_g",
            "lipidios_g": "lipideos_g",
            "fibra_g": "fibra_alimentar_g",
            "ferro_mg": "ferro_mg",
            "calcio_mg": "calcio_mg",
            "sodio_mg": "sodio_mg",
            "magnesio_mg": "magnesio_mg",
            "potassio_mg": "potassio_mg",
            "manganes_mg": "manganes_mg",
            "fosforo_mg": "fosforo_mg",
            "cobre_mg": "cobre_mg",
            "zinco_mg": "zinco_mg",
            "cinzas_g": "cinzas_g",
            "retinol_mcg": "retinol_ug",
            "tiamina_mg": "tiamina_mg",
            "riboflavina_mg": "riboflavina_mg",
            "piridoxina_mg": "piridoxina_mg",
            "niacina_mg": "niacina_mg",
            "umidade_percentual": "umidade",
        }

        nutrients: dict[str, str | None] = {}
        for output_key, source_key in key_map.items():
            nutrients[output_key] = self._extract_raw_value(data_window, source_key)
        return nutrients

    def _extract_slug(self, data_window: str) -> str | None:
        return self._extract_raw_value(data_window, "slug")

    def _load_public_index(self) -> list[TacoOnlineFoodIndexItem]:
        if self._cached_index is not None:
            return self._cached_index

        home_html = self.fetch_html(f"{TACO_ONLINE_BASE_URL}/")
        items = self._extract_public_index_items(home_html)
        self._cached_index = items
        self._logger.debug("TACO Online public index loaded with %d items", len(items))
        return items

    def _extract_public_index_items(self, html: str) -> list[TacoOnlineFoodIndexItem]:
        pattern = re.compile(
            r'\\\"slug\\\":\\\"(?P<slug>[^\\\"]+)\\\",'
            r'\\\"descricao\\\":\\\"(?P<descricao>[^\\\"]+)\\\",'
            r'\\\"grupo_slug\\\":\\\"(?P<grupo_slug>[^\\\"]*)\\\",'
            r'\\\"table\\\":\\\"(?P<table>[^\\\"]+)\\\",'
            r'\\\"grupo\\\":\\\"(?P<grupo>[^\\\"]*)\\\"',
            flags=re.IGNORECASE,
        )

        by_slug: dict[str, TacoOnlineFoodIndexItem] = {}
        for match in pattern.finditer(html):
            slug = _cleanup_raw_value(match.group("slug"))
            nome_alimento = _cleanup_raw_value(match.group("descricao"))
            tabela = _cleanup_raw_value(match.group("table"))
            grupo_alimentar = _cleanup_raw_value(match.group("grupo")) or None
            if not slug or not nome_alimento or not tabela:
                continue

            by_slug[slug] = TacoOnlineFoodIndexItem(
                slug=slug,
                nome_alimento=nome_alimento,
                grupo_alimentar=grupo_alimentar,
                tabela=tabela,
            )

        return list(by_slug.values())

    def _score_index_item(
        self,
        *,
        query_normalized: str,
        query_tokens: list[str],
        item: TacoOnlineFoodIndexItem,
    ) -> int:
        name_normalized = _normalize_text(item.nome_alimento)
        slug_normalized = _normalize_text(item.slug.replace("-", " "))

        score = 0
        if name_normalized == query_normalized:
            score += 240
        if query_normalized and query_normalized in name_normalized:
            score += 120
            if name_normalized.startswith(query_normalized):
                score += 20
        if query_normalized and query_normalized in slug_normalized:
            score += 100
            if slug_normalized.startswith(query_normalized):
                score += 20

        token_hits = sum(1 for token in query_tokens if token in name_normalized or token in slug_normalized)
        score += token_hits * 20
        if query_tokens and token_hits == len(query_tokens):
            score += 40

        return score

    def _find_food_window(self, html: str, expected_slug: str | None) -> str | None:
        positions: list[int] = []
        if expected_slug:
            escaped_pattern = re.compile(rf'\\\"slug\\\":\\\"{re.escape(expected_slug)}\\\"')
            plain_pattern = re.compile(rf'"slug":"{re.escape(expected_slug)}"')
            positions.extend(match.start() for match in escaped_pattern.finditer(html))
            positions.extend(match.start() for match in plain_pattern.finditer(html))

        for position in sorted(set(positions)):
            window = self._slice_window(html, position)
            if self._looks_like_nutrient_data(window):
                return window

        fallback_pattern = re.compile(r'(?:\\?"energia_kcal\\?")\s*:\s*')
        fallback_match = fallback_pattern.search(html)
        if fallback_match:
            window = self._slice_window(html, fallback_match.start())
            if self._looks_like_nutrient_data(window):
                return window

        return None

    def _slice_window(self, html: str, position: int) -> str:
        start = max(0, position - 3000)
        end = min(len(html), position + 14000)
        return html[start:end]

    def _looks_like_nutrient_data(self, text: str) -> bool:
        required_tokens = ("energia_kcal", "carboidrato_g", "proteina_g", "lipideos_g", "descricao")
        return all(token in text for token in required_tokens)

    def _extract_raw_value(self, text: str, key: str) -> str | None:
        pattern = re.compile(
            rf'(?:\\?"{re.escape(key)}\\?")\s*:\s*(?P<value>\\?"[^"]*\\?"|[^,\}}\]]+)',
            flags=re.IGNORECASE,
        )
        match = pattern.search(text)
        if not match:
            return None
        return _cleanup_raw_value(match.group("value"))


def _cleanup_raw_value(value: str) -> str:
    cleaned = value.strip().strip(",")

    if cleaned.startswith('\\"') and cleaned.endswith('\\"'):
        cleaned = cleaned[2:-2]
    elif cleaned.startswith('"') and cleaned.endswith('"'):
        cleaned = cleaned[1:-1]

    cleaned = cleaned.replace('\\"', '"')
    cleaned = cleaned.replace("\\n", " ").replace("\\t", " ")
    return " ".join(cleaned.split())


def _normalize_text(value: str) -> str:
    return normalize_pt_text(value)
