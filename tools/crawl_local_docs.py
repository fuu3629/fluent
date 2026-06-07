from __future__ import annotations

import argparse
import re
import time
from collections import deque
from http.client import RemoteDisconnected
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen


DEFAULT_START_URL = "http://127.0.0.1:50227/en/html/"
DEFAULT_SCOPE_URL = "http://127.0.0.1:50227/en/html/"
DEFAULT_OUTPUT_DIR = Path.home() / "Downloads" / "modefrontier-docs"
USER_AGENT = "local-docs-crawler/1.0"


class LinkParser(HTMLParser):
    """Collect local document links from common HTML attributes."""

    LINK_ATTRS = {"href", "src"}

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in self.LINK_ATTRS and value:
                self.links.append(value)


HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}


def normalize_url(url: str) -> str:
    url, _fragment = urldefrag(url)
    return url


def is_allowed_url(url: str, base_url: str) -> bool:
    parsed = urlparse(url)
    base = urlparse(base_url)
    return (
        parsed.scheme in {"http", "https"}
        and parsed.netloc == base.netloc
        and parsed.path.startswith(base.path)
    )


def local_path_for_url(url: str, base_url: str, output_dir: Path) -> Path:
    parsed = urlparse(url)
    base = urlparse(base_url)
    relative_path = parsed.path.removeprefix(base.path).lstrip("/")

    if not relative_path or relative_path.endswith("/"):
        relative_path = f"{relative_path}index.html"

    path = output_dir / relative_path

    if parsed.query:
        safe_query = re.sub(r"[^A-Za-z0-9_.-]+", "_", parsed.query)
        path = path.with_name(f"{path.name}_{safe_query}")

    if not path.suffix:
        path = path.with_suffix(".html")

    return path


def fetch(url: str, timeout: float) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get_content_type()
        return response.read(), content_type


def extract_links(body: bytes, url: str, content_type: str) -> Iterable[str]:
    if content_type not in HTML_CONTENT_TYPES:
        return []

    text = body.decode("utf-8", errors="ignore")
    parser = LinkParser()
    parser.feed(text)
    return (urljoin(url, item.strip()) for item in parser.links)


def scope_url_for(start_url: str, scope_url: str | None) -> str:
    if scope_url:
        scope_url = normalize_url(scope_url)
        return scope_url if scope_url.endswith("/") else scope_url.rsplit("/", 1)[0] + "/"

    start_url = normalize_url(start_url)
    parsed_start = urlparse(start_url)
    if not parsed_start.path.endswith("/"):
        return start_url.rsplit("/", 1)[0] + "/"
    return start_url


def crawl(
    start_url: str,
    scope_url: str | None,
    output_dir: Path,
    max_files: int,
    delay: float,
    timeout: float,
) -> None:
    start_url = normalize_url(start_url)
    allowed_scope_url = scope_url_for(start_url, scope_url)

    output_dir.mkdir(parents=True, exist_ok=True)

    queue: deque[str] = deque([start_url])
    seen: set[str] = set()
    saved = 0

    while queue and saved < max_files:
        url = normalize_url(queue.popleft())
        if url in seen or not is_allowed_url(url, allowed_scope_url):
            continue

        seen.add(url)

        try:
            body, content_type = fetch(url, timeout)
        except (HTTPError, URLError, TimeoutError, RemoteDisconnected, OSError) as exc:
            print(f"SKIP {url} ({exc})")
            continue

        if content_type not in HTML_CONTENT_TYPES:
            print(f"SKIP {url} (content-type: {content_type})")
            continue

        target = local_path_for_url(url, allowed_scope_url, output_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        saved += 1
        print(f"SAVE {saved:05d} {url} -> {target}")

        for link in extract_links(body, url, content_type):
            link = normalize_url(link)
            if link and is_allowed_url(link, allowed_scope_url) and link not in seen:
                queue.append(link)

        if delay:
            time.sleep(delay)

    print(f"Done. Saved {saved} files to {output_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mirror local HTML documentation, such as modeFRONTIER docs."
    )
    parser.add_argument("--start-url", default=DEFAULT_START_URL)
    parser.add_argument("--scope-url", default=DEFAULT_SCOPE_URL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-files", type=int, default=10000)
    parser.add_argument("--delay", type=float, default=0.02)
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    crawl(
        args.start_url,
        args.scope_url,
        args.output_dir,
        args.max_files,
        args.delay,
        args.timeout,
    )


if __name__ == "__main__":
    main()
