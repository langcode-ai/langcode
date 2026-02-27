"""web_fetch - Fetch content from a URL and return as markdown."""

from __future__ import annotations

import re
import urllib.error
import urllib.request

from langchain.tools import tool

from ..core.utils import truncate


def _html_to_text(html: str) -> str:
    """Very basic HTML to plain text conversion."""
    # Remove script/style
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Convert common block elements to newlines
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</(p|div|h[1-6]|li|tr)>", "\n", html, flags=re.IGNORECASE)
    # Strip remaining tags
    html = re.sub(r"<[^>]+>", "", html)
    # Decode common entities
    html = html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    html = html.replace("&quot;", '"').replace("&nbsp;", " ").replace("&#39;", "'")
    # Collapse whitespace
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


@tool("WebFetch")
def web_fetch(url: str, prompt: str = "") -> str:
    """Fetches content from a specified URL and processes it.

    Args:
        url: The URL to fetch content from. Must be a fully-formed valid URL (e.g. https://example.com).
        prompt: The prompt describing what information you want to extract from the page. When provided, the fetched content is filtered to the most relevant parts.

    Usage:
    - IMPORTANT: If an MCP-provided web fetch tool is available, prefer using that tool instead.
    - HTTP URLs will be automatically upgraded to HTTPS.
    - HTML content is converted to plain text (markdown).
    - Response is truncated if too large.
    - When a URL redirects to a different host, the tool will inform you — make a new WebFetch request with the redirect URL.
    - This tool is read-only and does not modify any files."""
    if url.startswith("http://"):
        url = "https://" + url[7:]
    if not url.startswith("https://"):
        url = "https://" + url

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "langcode/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(512 * 1024)  # max 512KB
            encoding = "utf-8"
            if "charset=" in content_type:
                encoding = content_type.split("charset=")[-1].split(";")[0].strip()
            text = raw.decode(encoding, errors="replace")

        if "html" in content_type.lower():
            text = _html_to_text(text)

        return truncate(text)
    except urllib.error.HTTPError as e:
        return f"Error: HTTP {e.code} {e.reason}"
    except urllib.error.URLError as e:
        return f"Error: {e.reason}"
    except Exception as e:
        return f"Error: {e}"
