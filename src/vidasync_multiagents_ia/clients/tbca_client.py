import logging
from time import perf_counter
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from vidasync_multiagents_ia.observability import record_external_request
from vidasync_multiagents_ia.observability.payload_preview import preview_text, sanitize_url
from vidasync_multiagents_ia.schemas import TBCAFoodCandidate, TBCANutrientRow

TBCA_BASE_URL = "https://www.tbca.net.br/base-dados/"
TBCA_SEARCH_PATH = "composicao_alimentos.php"
TBCA_DETAIL_HINT = "int_composicao_alimentos.php"


class TBCAClientError(RuntimeError):
    pass


class _SearchResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._inside_row = False
        self._inside_cell = False
        self._current_cell_href: str | None = None
        self._current_cell_text_parts: list[str] = []
        self._current_row_cells: list[tuple[str, str | None]] = []
        self._results_by_href: dict[str, TBCAFoodCandidate] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)

        if tag == "tr":
            self._inside_row = True
            self._current_row_cells = []
            return

        if tag == "td" and self._inside_row:
            self._inside_cell = True
            self._current_cell_href = None
            self._current_cell_text_parts = []
            return

        if tag == "a" and self._inside_cell:
            href = (attrs_dict.get("href") or "").strip()
            if TBCA_DETAIL_HINT in href and not self._current_cell_href:
                self._current_cell_href = href

    def handle_data(self, data: str) -> None:
        if self._inside_cell:
            text = data.strip()
            if text:
                self._current_cell_text_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._inside_cell:
            cell_text = _normalize_space(" ".join(self._current_cell_text_parts))
            self._current_row_cells.append((cell_text, self._current_cell_href))
            self._inside_cell = False
            return

        if tag == "tr" and self._inside_row:
            self._maybe_store_row()
            self._inside_row = False

    @property
    def results(self) -> list[TBCAFoodCandidate]:
        return list(self._results_by_href.values())

    def _maybe_store_row(self) -> None:
        if len(self._current_row_cells) < 2:
            return

        detail_path = next((href for _, href in self._current_row_cells if href), None)
        if not detail_path:
            return

        code = self._current_row_cells[0][0] or None
        name = self._current_row_cells[1][0]
        if not name:
            return

        if detail_path not in self._results_by_href:
            self._results_by_href[detail_path] = TBCAFoodCandidate(
                code=code,
                name=name,
                detail_path=detail_path,
            )


class _DetailNutrientTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._table_depth = 0
        self._target_table_depth: int | None = None
        self._inside_row = False
        self._inside_cell = False
        self._current_cell_text_parts: list[str] = []
        self._current_row_cells: list[str] = []
        self._rows_all_tables: list[TBCANutrientRow] = []
        self._rows_target_table: list[TBCANutrientRow] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)

        if tag == "table":
            self._table_depth += 1
            table_id = (attrs_dict.get("id") or "").strip().lower()
            if table_id == "tabela1" and self._target_table_depth is None:
                self._target_table_depth = self._table_depth
            return

        if tag == "tr" and self._table_depth > 0:
            self._inside_row = True
            self._current_row_cells = []
            return

        if tag == "td" and self._inside_row:
            self._inside_cell = True
            self._current_cell_text_parts = []

    def handle_data(self, data: str) -> None:
        if self._inside_cell:
            text = data.strip()
            if text:
                self._current_cell_text_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._inside_cell:
            cell_text = _normalize_space(" ".join(self._current_cell_text_parts))
            self._current_row_cells.append(cell_text)
            self._inside_cell = False
            return

        if tag == "tr" and self._inside_row:
            self._maybe_store_row()
            self._inside_row = False
            return

        if tag == "table" and self._table_depth > 0:
            if self._target_table_depth == self._table_depth:
                self._target_table_depth = None
            self._table_depth -= 1

    @property
    def rows(self) -> list[TBCANutrientRow]:
        if self._rows_target_table:
            return self._rows_target_table
        return self._rows_all_tables

    def _maybe_store_row(self) -> None:
        if len(self._current_row_cells) < 3:
            return

        component = self._current_row_cells[0]
        unit = self._current_row_cells[1]
        value = self._current_row_cells[2]

        if not component or component.lower() == "componente":
            return

        row = TBCANutrientRow(
            component=component,
            unit=unit,
            value_per_100g=value,
        )
        self._rows_all_tables.append(row)

        if self._target_table_depth is not None and self._table_depth >= self._target_table_depth:
            self._rows_target_table.append(row)


class TBCAClient:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
        *,
        log_payloads: bool = True,
        log_max_chars: int = 4000,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._logger = logging.getLogger(__name__)
        self._base_url = TBCA_BASE_URL
        self._search_url = urljoin(self._base_url, TBCA_SEARCH_PATH)
        self._log_payloads = log_payloads
        self._log_max_chars = max(256, log_max_chars)

    def search_foods(self, query: str) -> list[TBCAFoodCandidate]:
        search_url = f"{self._search_url}?{urlencode({'produto': query})}"
        self._logger.debug("TBCA search request url=%s", search_url)
        html = self._request_html(search_url)

        parser = _SearchResultsParser()
        parser.feed(html)
        return parser.results

    def fetch_food_nutrients(self, detail_path: str) -> tuple[str, list[TBCANutrientRow]]:
        detail_url = self._build_detail_url(detail_path)
        self._logger.debug("TBCA detail request url=%s", detail_url)
        html = self._request_html(detail_url)

        parser = _DetailNutrientTableParser()
        parser.feed(html)
        return detail_url, parser.rows

    def _build_detail_url(self, detail_path: str) -> str:
        if detail_path.startswith(("http://", "https://")):
            return detail_path
        return urljoin(self._base_url, detail_path.lstrip("/"))

    def _request_html(self, url: str) -> str:
        started = perf_counter()
        self._logger.info(
            "tbca.http.request",
            extra={
                "client": "tbca",
                "operation": "request_html",
                "url": sanitize_url(url),
                "timeout_seconds": self._timeout_seconds,
            },
        )
        request = Request(
            url=url,
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
                    "tbca.http.response",
                    extra={
                        "client": "tbca",
                        "operation": "request_html",
                        "url": sanitize_url(url),
                        "status_code": getattr(response, "status", 200),
                        "duration_ms": round(duration_ms, 4),
                        "response_size_bytes": len(content),
                        "response_preview": self._preview(decoded),
                    },
                )
                record_external_request(
                    client="tbca",
                    operation="request_html",
                    status=str(getattr(response, "status", 200)),
                    duration_ms=duration_ms,
                )
                return decoded
        except HTTPError as exc:
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.warning(
                "tbca.http.error",
                extra={
                    "client": "tbca",
                    "operation": "request_html",
                    "url": sanitize_url(url),
                    "status_code": exc.code,
                    "duration_ms": round(duration_ms, 4),
                    "error_type": "HTTPError",
                },
            )
            record_external_request(client="tbca", operation="request_html", status=str(exc.code), duration_ms=duration_ms)
            raise TBCAClientError(f"TBCA HTTP error while requesting '{url}': {exc.code}") from exc
        except URLError as exc:
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.warning(
                "tbca.http.error",
                extra={
                    "client": "tbca",
                    "operation": "request_html",
                    "url": sanitize_url(url),
                    "status_code": "network_error",
                    "duration_ms": round(duration_ms, 4),
                    "error_type": "URLError",
                },
            )
            record_external_request(client="tbca", operation="request_html", status="network_error", duration_ms=duration_ms)
            raise TBCAClientError(f"TBCA network error while requesting '{url}'.") from exc
        except TimeoutError as exc:
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.warning(
                "tbca.http.error",
                extra={
                    "client": "tbca",
                    "operation": "request_html",
                    "url": sanitize_url(url),
                    "status_code": "timeout",
                    "duration_ms": round(duration_ms, 4),
                    "error_type": "TimeoutError",
                },
            )
            record_external_request(client="tbca", operation="request_html", status="timeout", duration_ms=duration_ms)
            raise TBCAClientError(f"TBCA request timeout while requesting '{url}'.") from exc

    def _preview(self, raw: str) -> str | None:
        if not self._log_payloads:
            return None
        return preview_text(raw, max_chars=self._log_max_chars)


def _normalize_space(text: str) -> str:
    return " ".join(text.split())
