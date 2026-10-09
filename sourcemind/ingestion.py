"""Page-preserving PDF ingestion and bounded public URL fetches."""
from __future__ import annotations

import ipaddress
import io
import re
import socket
import time
from urllib.parse import urlsplit, urljoin

from .engine import fingerprint

MAX_BYTES = 15 * 1024 * 1024
MAX_PAGES = 200
MAX_CHUNKS = 500


def split_page(text: str, size: int = 1000, overlap: int = 180) -> list[str]:
    text = text.replace("\x00", "").strip()
    chunks, start = [], 0
    while start < len(text):
        end = min(start+size, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n", start+size//2, end), text.rfind(". ", start+size//2, end))
            if boundary > start:
                end = boundary+1
        value = text[start:end].strip()
        if len(value) >= 30:
            chunks.append(value)
        if end == len(text):
            break
        start = max(start+1, end-overlap)
    return chunks


def build_document(name: str, kind: str, pages: list[tuple[int | None, str]]) -> dict:
    chunks = [{"page": page, "ordinal": i, "content": text}
              for page, page_text in pages for i, text in enumerate(split_page(page_text))]
    for i, chunk in enumerate(chunks):
        chunk["ordinal"] = i
    if not chunks:
        raise ValueError("No readable text was found. Scanned PDFs need OCR before upload.")
    if len(chunks) > MAX_CHUNKS:
        raise ValueError(f"This source exceeds the {MAX_CHUNKS}-passage limit. Split it into smaller PDFs.")
    # Include every page, not just the first 500 characters of the first page.
    fp = fingerprint("\n\f\n".join(text for _, text in pages))
    return {"name": name[:500], "source_type": kind, "fingerprint": fp, "chunks": chunks,
            "summary": " ".join(pages[0][1].split())[:400], "page_count": len(pages)}


def read_pdf(data: bytes, name: str) -> dict:
    from pypdf import PdfReader
    if len(data) > MAX_BYTES:
        raise ValueError("PDFs must be smaller than 15 MB.")
    if not data.lstrip().startswith(b"%PDF-"):
        raise ValueError("The upload is not a PDF.")
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("Remove this PDF's password before uploading.")
    if len(reader.pages) > MAX_PAGES:
        raise ValueError(f"Upload at most {MAX_PAGES} pages per PDF.")
    pages = [(i+1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
    return build_document(name, "pdf", pages)


def validate_public_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("Use a public http(s) URL without credentials.")
    if parts.port not in (None, 80, 443):
        raise ValueError("Only standard web ports are allowed.")
    addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("Private, loopback and internal network addresses are blocked.")
    return url


def read_url(url: str) -> dict:
    import bs4
    import requests
    # Validate each redirect before fetching; proxy environment variables are
    # disabled. Deployment-level egress restrictions should also block private IPs
    # to cover DNS rebinding between resolution and the network connection.
    with requests.Session() as session:
        session.trust_env = False
        deadline = time.monotonic()+25
        for _ in range(5):
            validate_public_url(url)
            with session.get(url, headers={"User-Agent": "SourceMind/2.0"}, timeout=(5, 8),
                             allow_redirects=False, stream=True) as response:
                if 300 <= response.status_code < 400:
                    location = response.headers.get("Location")
                    if not location:
                        raise ValueError("Redirect without a destination.")
                    url = urljoin(url, location)
                    continue
                response.raise_for_status()
                if "text/html" not in response.headers.get("Content-Type", "").lower():
                    raise ValueError("This URL is not an HTML page. Upload PDF files directly.")
                data = bytearray()
                for block in response.iter_content(65536):
                    data.extend(block)
                    if len(data) > MAX_BYTES or time.monotonic() > deadline:
                        raise ValueError("This page exceeded the download size or time limit.")
                soup = bs4.BeautifulSoup(bytes(data), "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe"]):
                    tag.decompose()
                content = soup.select_one("article, main, [role='main']") or soup.body or soup
                text = re.sub(r"[ \t]+", " ", content.get_text("\n", strip=True))
                return build_document(url, "url", [(None, text)])
    raise ValueError("Too many redirects.")
