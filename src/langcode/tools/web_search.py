"""web_search - Search the web via DuckDuckGo and return results."""

from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request

from langchain.tools import tool

from ..core.utils import truncate


@tool("WebSearch")
def web_search(
    query: str,
    allowed_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
) -> str:
    """Search the web and use the results to inform responses. Provides up-to-date information for current events and recent data. Returns search result information including titles, URLs, and snippets.

    CRITICAL REQUIREMENT - You MUST follow this:
    - After answering the user's question, you MUST include a "Sources:" section at the end of your response
    - In the Sources section, list all relevant URLs from the search results as markdown hyperlinks: [Title](URL)
    - This is MANDATORY — never skip including sources in your response

    IMPORTANT: Use the correct year in search queries. When searching for recent information, documentation, or current events, always use the current year in your query.

    Args:
        query: The search query to use. Be specific and include relevant keywords. Include version numbers or dates when relevant.
        allowed_domains: Only include search results from these domains (domain filtering).
        blocked_domains: Never include search results from these domains."""
    try:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read(256 * 1024).decode("utf-8", errors="replace")

        results = []
        blocks = re.findall(
            r'<a[^>]+class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        )
        for href, title, snippet in blocks:
            title = re.sub(r"<[^>]+>", "", title).strip()
            snippet = re.sub(r"<[^>]+>", "", snippet).strip()
            if "uddg=" in href:
                real = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg", [href])
                href = real[0] if real else href

            # Domain filtering
            try:
                domain = urllib.parse.urlparse(href).netloc.lower().lstrip("www.")
            except Exception:
                domain = ""

            if allowed_domains and not any(
                domain == d.lstrip("www.") or domain.endswith("." + d.lstrip("www."))
                for d in allowed_domains
            ):
                continue
            if blocked_domains and any(
                domain == d.lstrip("www.") or domain.endswith("." + d.lstrip("www."))
                for d in blocked_domains
            ):
                continue

            results.append(f"**{title}**\n{href}\n{snippet}")
            if len(results) >= 10:
                break

        if not results:
            return f"No results found for: {query}"
        return truncate("\n\n".join(results))
    except Exception as e:
        return f"Error searching: {e}"
