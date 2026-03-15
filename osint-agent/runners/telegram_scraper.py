"""Telegram public channel scraper — extracts posts from public channels
without API keys. Uses the t.me/s/ public embed view.

Also supports regional search by scraping multiple OSINT channels for
mentions of a location/keyword.
"""

import datetime
import logging
import re
import urllib.parse
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from runners.base import BaseToolRunner

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Well-known OSINT / intelligence Telegram channels for regional search
OSINT_CHANNELS = [
    "inaborwegian",         # OSINT updates
    "osaborwegian",         # OSINT aggregator
    "CyberNewsUpdate",      # Cyber threat news
    "breakaborwegian",      # Breaking news
    "WarMonitor3",          # Conflict monitoring
    "IntelSlava",           # Geopolitical intelligence
    "MilitaryRussian",      # Military OSINT
    "ukraine_update_news",  # Ukraine conflict
    "TheIntelArena",        # Intelligence arena
    "GeromanAT",            # Geopolitical analysis
    "ryaborwegian",         # Russian military
    "naborwegianews",       # News aggregator
    "aborwegiandangerous",  # OSINT
]


def _parse_posts(html: str, base_url: str, limit: int = 50) -> list[dict]:
    """Parse Telegram embed page HTML into structured post dicts."""
    soup = BeautifulSoup(html, "html.parser")
    posts_divs = soup.find_all("div", attrs={"class": "tgme_widget_message", "data-post": True})
    posts = []

    for post_div in reversed(posts_divs):
        if len(posts) >= limit:
            break
        try:
            # Date
            date_div = post_div.find("div", class_="tgme_widget_message_footer")
            date_a = date_div.find("a", class_="tgme_widget_message_date") if date_div else None
            if not date_a:
                continue
            raw_url = date_a["href"]
            url = raw_url.replace("//t.me/", "//t.me/s/")

            time_tag = date_a.find("time", datetime=True)
            if time_tag:
                date_str = time_tag["datetime"]
                date = datetime.datetime.fromisoformat(date_str)
            else:
                date = None

            # Content
            msg_div = post_div.find("div", class_="tgme_widget_message_text")
            content = msg_div.get_text(separator="\n").strip() if msg_div else ""

            # Outlinks
            outlinks = []
            for link in post_div.find_all("a", href=True):
                href = link["href"]
                parent_classes = link.parent.get("class", [])
                if any(x in parent_classes for x in ("tgme_widget_message_user", "tgme_widget_message_author")):
                    continue
                if href == raw_url or href == url:
                    continue
                resolved = urllib.parse.urljoin(base_url, href)
                if resolved not in outlinks:
                    outlinks.append(resolved)

            # Link preview
            preview = None
            preview_a = post_div.find("a", class_="tgme_widget_message_link_preview")
            if preview_a:
                preview = {"href": urllib.parse.urljoin(base_url, preview_a.get("href", ""))}
                site_name = preview_a.find("div", class_="link_preview_site_name")
                if site_name:
                    preview["site"] = site_name.text
                title = preview_a.find("div", class_="link_preview_title")
                if title:
                    preview["title"] = title.text
                desc = preview_a.find("div", class_="link_preview_description")
                if desc:
                    preview["description"] = desc.text

            # Views
            views_span = post_div.find("span", class_="tgme_widget_message_views")
            views = views_span.text.strip() if views_span else None

            posts.append({
                "url": raw_url,
                "date": date.isoformat() if date else None,
                "content": content,
                "outlinks": outlinks[:5],
                "preview": preview,
                "views": views,
                "channel": post_div["data-post"].split("/")[0],
            })
        except Exception as e:
            logger.debug(f"Failed to parse Telegram post: {e}")
            continue

    return posts


class TelegramScraperRunner(BaseToolRunner):
    tool_name = "telegram_scraper"
    cache_ttl = 300  # 5 min cache

    async def scrape_channel(self, channel: str, limit: int = 20) -> dict:
        """Scrape recent posts from a public Telegram channel."""
        channel = channel.lstrip("@").strip()
        cache_key = self._cache_key("channel", channel)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(f"https://t.me/s/{channel}", headers=_HEADERS)
                if resp.status_code != 200:
                    return {"status": "error", "error": f"HTTP {resp.status_code}", "channel": channel, "posts": []}
                if "/s/" not in str(resp.url):
                    return {"status": "error", "error": "Channel has no public posts", "channel": channel, "posts": []}

                posts = _parse_posts(resp.text, str(resp.url), limit=limit)

                # Get channel info
                info_resp = await client.get(f"https://t.me/{channel}", headers=_HEADERS)
                channel_info = {}
                if info_resp.status_code == 200:
                    soup = BeautifulSoup(info_resp.text, "html.parser")
                    title_div = soup.find("div", class_="tgme_page_title")
                    if title_div:
                        channel_info["title"] = title_div.get_text(strip=True)
                    desc_div = soup.find("div", class_="tgme_page_description")
                    if desc_div:
                        channel_info["description"] = desc_div.get_text(strip=True)
                    extra_div = soup.find("div", class_="tgme_page_extra")
                    if extra_div and "subscribers" in extra_div.text:
                        channel_info["members"] = extra_div.text.strip().replace(" subscribers", "").replace(" ", "")
                    photo_img = soup.find("img", class_="tgme_page_photo_image")
                    if photo_img:
                        channel_info["photo"] = photo_img.get("src", "")

        except Exception as e:
            logger.warning(f"Telegram scrape failed for {channel}: {e}")
            return {"status": "error", "error": str(e), "channel": channel, "posts": []}

        output = {
            "status": "ok",
            "channel": channel,
            "channel_info": channel_info,
            "total": len(posts),
            "posts": posts,
        }
        self._set_cached(cache_key, output)
        return output

    async def search_channels(self, query: str, channels: list[str] = None, limit: int = 5) -> dict:
        """Search multiple Telegram channels for posts mentioning a keyword.

        Used for regional intelligence — searches OSINT channels for a location name.
        """
        cache_key = self._cache_key("search", query)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        search_channels = channels or OSINT_CHANNELS
        query_lower = query.lower()
        matching_posts = []

        import asyncio
        tasks = []
        for ch in search_channels:
            tasks.append(self._search_single_channel(ch, query_lower, limit=20))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                matching_posts.extend(result)

        # Sort by date (newest first) and limit
        matching_posts.sort(key=lambda p: p.get("date", ""), reverse=True)
        matching_posts = matching_posts[:limit * 3]  # Return more for regional context

        output = {
            "status": "ok",
            "query": query,
            "channels_searched": len(search_channels),
            "total": len(matching_posts),
            "posts": matching_posts,
        }
        self._set_cached(cache_key, output)
        return output

    async def _search_single_channel(self, channel: str, query_lower: str, limit: int = 20) -> list[dict]:
        """Scrape a single channel and filter posts by keyword."""
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(f"https://t.me/s/{channel}", headers=_HEADERS)
                if resp.status_code != 200 or "/s/" not in str(resp.url):
                    return []
                posts = _parse_posts(resp.text, str(resp.url), limit=limit)
                return [p for p in posts if query_lower in (p.get("content", "") or "").lower()]
        except Exception:
            return []
