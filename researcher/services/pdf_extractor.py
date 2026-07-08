from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, cast

import fitz  # PyMuPDF
import requests

from researcher.constants import MIN_PDF_TEXT_CHARS


class PDFExtractionError(Exception):
    """Raised when PDF fetching or extraction fails."""


@dataclass
class PDFPageText:
    page_number: int
    text: str


@dataclass
class PDFExtractionResult:
    url: str
    final_url: str
    title: Optional[str]
    text: str
    pages: List[PDFPageText] = field(default_factory=list)
    page_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    extraction_method: str = "pymupdf"


class PDFExtractor:
    """
    Primary PDF extractor using requests + PyMuPDF.

    Responsibilities:
    - download PDF bytes
    - extract text page by page
    - return normalized extraction output
    - surface weak/failed extraction clearly
    """

    def __init__(
        self,
        timeout_seconds: int = 30,
        user_agent: Optional[str] = None,
        min_text_chars: int = MIN_PDF_TEXT_CHARS,
        include_page_text: bool = True,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        self.min_text_chars = min_text_chars
        self.include_page_text = include_page_text

    def extract(self, url: str) -> PDFExtractionResult:
        """
        Fetch a PDF and extract text with PyMuPDF.
        """
        pdf_bytes, final_url, title_hint = self._download_pdf(url)
        return self._extract_from_bytes(
            pdf_bytes=pdf_bytes,
            source_url=url,
            final_url=final_url,
            title_hint=title_hint,
        )

    def extract_from_bytes(
        self,
        pdf_bytes: bytes,
        *,
        source_url: str = "memory://pdf",
        final_url: Optional[str] = None,
        title_hint: Optional[str] = None,
    ) -> PDFExtractionResult:
        """
        Extract text from already-available PDF bytes.
        Useful for testing or future integrations.
        """
        return self._extract_from_bytes(
            pdf_bytes=pdf_bytes,
            source_url=source_url,
            final_url=final_url or source_url,
            title_hint=title_hint,
        )

    def _download_pdf(self, url: str) -> tuple[bytes, str, Optional[str]]:
        """
        Download raw PDF bytes.
        """
        try:
            response = requests.get(
                url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout_seconds,
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise PDFExtractionError(f"Failed to fetch PDF url='{url}': {exc}") from exc

        content_type = response.headers.get("Content-Type", "").lower()
        if "pdf" not in content_type and not str(response.url).lower().endswith(".pdf"):
            raise PDFExtractionError(
                f"URL does not appear to be a PDF: url='{url}', content_type='{content_type}'"
            )

        pdf_bytes = response.content
        if not pdf_bytes:
            raise PDFExtractionError(f"Fetched empty PDF bytes for url='{url}'.")

        title_hint = self._infer_title_from_headers(response.headers)
        return pdf_bytes, str(response.url), title_hint

    def _extract_from_bytes(
        self,
        *,
        pdf_bytes: bytes,
        source_url: str,
        final_url: str,
        title_hint: Optional[str],
    ) -> PDFExtractionResult:
        """
        Parse PDF bytes with MarkItDown; fall back to PyMuPDF page extraction.
        """
        markitdown_result = self._extract_with_markitdown(
            pdf_bytes=pdf_bytes,
            source_url=source_url,
            final_url=final_url,
            title_hint=title_hint,
        )
        if markitdown_result is not None:
            return markitdown_result

        try:
            document = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
        except Exception as exc:
            raise PDFExtractionError(
                f"PyMuPDF failed to open PDF from '{source_url}': {exc}"
            ) from exc

        pages: List[PDFPageText] = []
        page_text_chunks: List[str] = []

        try:
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                raw_page_text = cast(str, page.get_text("text"))
                page_text = raw_page_text.strip()

                if self.include_page_text:
                    pages.append(
                        PDFPageText(
                            page_number=page_index + 1,
                            text=page_text,
                        )
                    )

                if page_text:
                    page_text_chunks.append(page_text)

            combined_text = "\n\n".join(page_text_chunks).strip()

            if len(combined_text) < self.min_text_chars:
                raise PDFExtractionError(
                    f"Extracted PDF text too short for url='{source_url}'. "
                    f"Got {len(combined_text)} chars, expected at least {self.min_text_chars}."
                )

            metadata = self._normalize_metadata(document.metadata or {})
            title = metadata.get("title") or title_hint

            return PDFExtractionResult(
                url=source_url,
                final_url=final_url,
                title=title,
                text=combined_text,
                pages=pages,
                page_count=document.page_count,
                metadata=metadata,
            )
        finally:
            document.close()

    def _extract_with_markitdown(
        self,
        *,
        pdf_bytes: bytes,
        source_url: str,
        final_url: str,
        title_hint: Optional[str],
    ) -> Optional[PDFExtractionResult]:
        """
        Convert PDF bytes to Markdown text with MarkItDown.

        Returns None on any failure so the caller can fall back to PyMuPDF.
        MarkItDown has no page boundaries, so `pages` stays empty (all
        consumers guard on empty pages).
        """
        try:
            from markitdown import MarkItDown

            converted = MarkItDown(enable_plugins=False).convert_stream(
                io.BytesIO(pdf_bytes), file_extension=".pdf"
            )
            text = (converted.text_content or "").strip()
        except Exception:
            return None

        if len(text) < self.min_text_chars:
            return None

        title = getattr(converted, "title", None) or title_hint
        return PDFExtractionResult(
            url=source_url,
            final_url=final_url,
            title=title,
            text=text,
            pages=[],
            page_count=0,
            metadata={},
            extraction_method="markitdown",
        )

    def _normalize_metadata(self, raw_metadata: Mapping[str, Any]) -> dict[str, str]:
        """
        Normalize PyMuPDF metadata into a clean string-only dict.
        """
        normalized: dict[str, str] = {}

        for key, value in raw_metadata.items():
            if value is None:
                continue

            key_str = str(key).strip()
            value_str = str(value).strip()

            if key_str and value_str:
                normalized[key_str] = value_str

        return normalized

    def _infer_title_from_headers(self, headers: Mapping[str, str]) -> Optional[str]:
        """
        Best-effort title inference from HTTP headers.
        """
        content_disposition = headers.get("Content-Disposition")
        if not content_disposition:
            return None

        lower_value = content_disposition.lower()
        if "filename=" not in lower_value:
            return None

        filename_part = content_disposition.split("filename=", maxsplit=1)[-1].strip()
        filename_part = filename_part.strip('"').strip("'")

        if filename_part.lower().endswith(".pdf"):
            filename_part = filename_part[:-4]

        filename_part = filename_part.strip()
        return filename_part or None
