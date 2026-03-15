"""Regional news & social media fetcher.

Actively searches for news, articles, and social posts about a specific region
using web searches, news aggregator APIs, and social media search endpoints.
"""

import logging
import re
import time
import requests
import feedparser
import concurrent.futures
from urllib.parse import quote, quote_plus

logger = logging.getLogger(__name__)

# Cache to avoid hammering APIs on every 60s refresh
_cache: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 180  # 3 minutes


def _get_cached(key: str) -> dict | None:
    if key in _cache:
        ts, data = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            return data
        del _cache[key]
    return None


def _set_cached(key: str, data: dict):
    _cache[key] = (time.time(), data)


_HEADERS = {'User-Agent': 'ShadowLens/1.0 (OSINT research)'}

# ISO2 → GDELT FIPS
_ISO2_TO_FIPS = {
    'US': 'US', 'GB': 'UK', 'FR': 'FR', 'DE': 'GM', 'RU': 'RS', 'CN': 'CH',
    'JP': 'JA', 'IN': 'IN', 'BR': 'BR', 'AU': 'AS', 'CA': 'CA', 'IT': 'IT',
    'ES': 'SP', 'MX': 'MX', 'KR': 'KS', 'TR': 'TU', 'SA': 'SA', 'UA': 'UP',
    'PL': 'PL', 'NL': 'NL', 'SE': 'SW', 'NO': 'NO', 'IL': 'IS', 'EG': 'EG',
    'ZA': 'SF', 'NG': 'NI', 'AR': 'AR', 'CO': 'CO', 'PK': 'PK', 'IR': 'IR',
    'IQ': 'IZ', 'SY': 'SY', 'AF': 'AF', 'TW': 'TW', 'PH': 'RP', 'TH': 'TH',
}


def _build_region_keywords(region_name: str) -> list[str]:
    """Build keyword list for strict region filtering."""
    parts = [p.strip() for p in region_name.split(',')]
    locality = parts[0].lower() if parts else ''
    state_region = parts[-1].strip().lower() if len(parts) > 1 else ''
    keywords = []
    if locality and len(locality) > 2:
        keywords.append(locality)
    if state_region and len(state_region) > 2 and state_region != locality:
        keywords.append(state_region)
    return keywords


def _filter_news(items: list[dict], region_keywords: list[str]) -> list[dict]:
    """Keep only items that mention the region in title/description."""
    if not region_keywords:
        return items
    filtered = []
    for item in items:
        text = (item.get('title', '') + ' ' + item.get('description', '')).lower()
        if any(kw in text for kw in region_keywords):
            filtered.append(item)
    return filtered


def fetch_regional_feeds_streaming(lat: float, lng: float, region_name: str, country_code: str):
    """Generator that yields (source_type, category, items) as each source completes.

    category is 'news' or 'social'. Used by the SSE streaming endpoint.
    """
    search_terms = _build_search_terms(region_name, country_code)
    news_queries = _build_news_queries(region_name, country_code)
    region_keywords = _build_region_keywords(region_name)
    logger.info(f"Regional stream: terms={search_terms}, news_queries={news_queries}")

    seen_titles: set[str] = set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_search_google_news, news_queries, lat, lng): ('google_news', 'news'),
            pool.submit(_search_bing_news, news_queries, lat, lng): ('bing_news', 'news'),
            pool.submit(_search_gdelt, country_code, search_terms, lat, lng): ('gdelt', 'news'),
            pool.submit(_search_reddit, search_terms): ('reddit', 'social'),
            pool.submit(_search_bluesky, search_terms): ('bluesky', 'social'),
            pool.submit(_search_mastodon, search_terms): ('mastodon', 'social'),
            pool.submit(_search_duckduckgo_news, news_queries, lat, lng): ('ddg_news', 'news'),
            pool.submit(_search_rss_regional, region_name, country_code, lat, lng): ('rss', 'news'),
            pool.submit(_search_telegram, search_terms): ('telegram', 'social'),
        }

        for future in concurrent.futures.as_completed(futures, timeout=45):
            source_name, category = futures[future]
            try:
                result = future.result(timeout=20)
                if not result:
                    continue
                # Filter news for region relevance
                if category == 'news':
                    result = _filter_news(result, region_keywords)
                # Deduplicate within stream
                deduped = []
                for item in result:
                    key = item.get('title', '')[:50].lower().strip()
                    if key and key not in seen_titles:
                        seen_titles.add(key)
                        deduped.append(item)
                if deduped:
                    yield (source_name, category, deduped)
            except Exception as e:
                logger.debug(f"Regional stream {source_name} failed: {e}")


def fetch_regional_feeds(lat: float, lng: float, region_name: str, country_code: str) -> dict:
    """Search for news, articles, and social posts about a specific region.

    Does active web searches — Google News, Bing News, GDELT, Reddit search,
    Bluesky search, Mastodon search — all querying the region name directly.
    """
    cache_key = f"regional_{country_code}_{region_name}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    # Build search queries from region info
    # e.g. "Nashville, Tennessee" or "Tennessee" or "France"
    search_terms = _build_search_terms(region_name, country_code)

    news = []
    social = []

    # News-specific queries with "breaking news" / "news today" keywords
    news_queries = _build_news_queries(region_name, country_code)
    logger.info(f"Regional search: terms={search_terms}, news_queries={news_queries}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_search_google_news, news_queries, lat, lng): 'google_news',
            pool.submit(_search_bing_news, news_queries, lat, lng): 'bing_news',
            pool.submit(_search_gdelt, country_code, search_terms, lat, lng): 'gdelt',
            pool.submit(_search_reddit, search_terms): 'reddit',
            pool.submit(_search_bluesky, search_terms): 'bluesky',
            pool.submit(_search_mastodon, search_terms): 'mastodon',
            pool.submit(_search_duckduckgo_news, news_queries, lat, lng): 'ddg_news',
            pool.submit(_search_rss_regional, region_name, country_code, lat, lng): 'rss',
            pool.submit(_search_telegram, search_terms): 'telegram',
        }

        for future in concurrent.futures.as_completed(futures, timeout=45):
            source = futures[future]
            try:
                result = future.result(timeout=20)
                if source in ('reddit', 'bluesky', 'mastodon', 'telegram'):
                    social.extend(result)
                else:
                    news.extend(result)
            except Exception as e:
                logger.debug(f"Regional {source} search failed: {e}")

    # Deduplicate news by title similarity
    news = _deduplicate(news)

    # STRICT filter: only keep articles whose title or description actually
    # mentions the locality or region.  Search engines often return unrelated
    # results even with targeted queries, so we filter EVERYTHING.
    parts = [p.strip() for p in region_name.split(',')]
    locality = parts[0].lower() if parts else ''
    state_region = parts[-1].strip().lower() if len(parts) > 1 else ''
    # Build keyword set: locality name, state/region, and any multi-word parts
    region_keywords = []
    if locality and len(locality) > 2:
        region_keywords.append(locality)
    if state_region and len(state_region) > 2 and state_region != locality:
        region_keywords.append(state_region)
    # Also add abbreviations / common short forms if we can derive them
    # e.g. "South Carolina" → also match "SC" as standalone word handled below

    filtered_news = []
    for item in news:
        text = (item.get('title', '') + ' ' + item.get('description', '')).lower()
        if any(kw in text for kw in region_keywords):
            filtered_news.append(item)
    news = filtered_news

    result = {
        'news': news[:150],
        'social_media': social[:100],
        'region': region_name,
        'country': country_code,
    }
    _set_cached(cache_key, result)
    return result


def _build_search_terms(region_name: str, country_code: str) -> list[str]:
    """Build a list of search terms from region name.

    Returns plain locality/region names for social search,
    plus news-oriented variants for news search engines.
    """
    terms = []
    if region_name and region_name != country_code:
        terms.append(region_name)
        parts = [p.strip() for p in region_name.split(',')]
        if len(parts) > 1:
            terms.append(parts[-1])  # state/country part
            terms.append(parts[0])   # city part
    if country_code and country_code not in terms:
        terms.append(country_code)
    return terms[:4]


def _build_news_queries(region_name: str, country_code: str) -> list[str]:
    """Build news-specific search queries with 'breaking news' keywords.

    Always pairs locality with state/region so results are geographically precise.
    e.g. "Charleston South Carolina news" not just "Charleston news".
    """
    queries = []
    parts = [p.strip() for p in region_name.split(',')]
    locality = parts[0] if parts else region_name
    state_region = parts[-1] if len(parts) > 1 else ''

    if locality and state_region and state_region != locality:
        # Best: locality + state together for disambiguation
        queries.append(f'"{locality}" "{state_region}" news')
        queries.append(f"{locality} {state_region} breaking news today")
        queries.append(f"{locality} {state_region} news")
    elif locality:
        queries.append(f'"{locality}" news today')
        queries.append(f"{locality} breaking news")
    if state_region and state_region != locality:
        queries.append(f"{state_region} news today")
    return queries[:4]


def _deduplicate(items: list[dict]) -> list[dict]:
    """Remove duplicate articles by title similarity."""
    seen = set()
    unique = []
    for item in items:
        key = item.get('title', '')[:50].lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


# ---------------------------------------------------------------------------
# Google News RSS Search
# ---------------------------------------------------------------------------
def _search_google_news(queries: list[str], lat: float, lng: float) -> list:
    """Search Google News RSS for breaking news in the region."""
    results = []
    for query in queries[:3]:
        try:
            url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en&gl=US&ceid=US:en"
            feed = feedparser.parse(url)
            for entry in feed.entries[:30]:
                # Extract actual source from title (Google News format: "Title - Source")
                title = entry.get('title', '')
                source = ''
                if ' - ' in title:
                    parts = title.rsplit(' - ', 1)
                    title = parts[0]
                    source = parts[1] if len(parts) > 1 else ''

                results.append({
                    'title': title,
                    'link': entry.get('link', ''),
                    'source': source or 'Google News',
                    'published': entry.get('published', ''),
                    'image_url': '',
                    'lat': lat,
                    'lon': lng,
                    'risk_score': 0.5,
                    'source_type': 'google_news',
                })
        except Exception as e:
            logger.debug(f"Google News search '{query}': {e}")
    return results


# ---------------------------------------------------------------------------
# Bing News RSS Search
# ---------------------------------------------------------------------------
def _search_bing_news(queries: list[str], lat: float, lng: float) -> list:
    """Search Bing News RSS for breaking news in the region."""
    results = []
    for query in queries[:3]:
        try:
            url = f"https://www.bing.com/news/search?q={quote_plus(query)}&format=rss"
            feed = feedparser.parse(url)
            for entry in feed.entries[:25]:
                results.append({
                    'title': entry.get('title', ''),
                    'link': entry.get('link', ''),
                    'source': entry.get('source', {}).get('title', 'Bing News') if hasattr(entry.get('source', ''), 'get') else 'Bing News',
                    'published': entry.get('published', ''),
                    'description': entry.get('summary', '')[:200],
                    'image_url': '',
                    'lat': lat,
                    'lon': lng,
                    'risk_score': 0.5,
                    'source_type': 'bing_news',
                })
        except Exception as e:
            logger.debug(f"Bing News search '{query}': {e}")
    return results


# ---------------------------------------------------------------------------
# DuckDuckGo News Search
# ---------------------------------------------------------------------------
def _search_duckduckgo_news(queries: list[str], lat: float, lng: float) -> list:
    """Search DuckDuckGo for breaking news about the region."""
    results = []
    for query in queries[:3]:
        try:
            url = f"https://duckduckgo.com/news.js?q={quote_plus(query)}&df=d&l=us-en"
            resp = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0'
            })
            if resp.status_code != 200:
                continue
            data = resp.json()
            for item in data.get('results', [])[:25]:
                results.append({
                    'title': item.get('title', ''),
                    'link': item.get('url', ''),
                    'source': item.get('source', 'DuckDuckGo'),
                    'published': item.get('date', ''),
                    'description': item.get('excerpt', '')[:200],
                    'image_url': item.get('image', ''),
                    'lat': lat,
                    'lon': lng,
                    'risk_score': 0.5,
                    'source_type': 'ddg_news',
                })
        except Exception as e:
            logger.debug(f"DDG News search '{query}': {e}")
    return results


# ---------------------------------------------------------------------------
# GDELT DOC API
# ---------------------------------------------------------------------------
def _search_gdelt(country_code: str, terms: list[str], lat: float, lng: float) -> list:
    """Search GDELT DOC API for articles about the region."""
    results = []

    # Try country-code query first
    fips = _ISO2_TO_FIPS.get(country_code, '')
    queries = []
    if fips:
        queries.append(f"sourcecountry:{fips}")
    # Also try keyword query with region name
    for term in terms[:1]:
        if len(term) > 2:
            queries.append(f'"{term}"')

    for query in queries[:2]:
        try:
            url = (
                f"https://api.gdeltproject.org/api/v2/doc/doc"
                f"?query={quote(query)}&mode=artlist&format=json"
                f"&maxrecords=50&timespan=24h&sort=datedesc"
            )
            resp = requests.get(url, timeout=15, headers=_HEADERS)
            if resp.status_code != 200:
                continue
            for art in resp.json().get('articles', [])[:50]:
                results.append({
                    'title': art.get('title', ''),
                    'link': art.get('url', ''),
                    'source': art.get('domain', ''),
                    'published': art.get('seendate', ''),
                    'image_url': art.get('socialimage', ''),
                    'lat': lat,
                    'lon': lng,
                    'risk_score': 0.5,
                    'source_type': 'gdelt_regional',
                    'country_code': country_code,
                })
        except Exception as e:
            logger.debug(f"GDELT search '{query}': {e}")
    return results


# ---------------------------------------------------------------------------
# Region-Specific RSS Feeds
# ---------------------------------------------------------------------------
_COUNTRY_RSS: dict[str, list[tuple[str, str]]] = {
    'US': [
        ('AP US', 'https://rsshub.app/apnews/topics/apf-usnews'),
        ('NPR', 'https://feeds.npr.org/1001/rss.xml'),
        ('CNN US', 'http://rss.cnn.com/rss/cnn_us.rss'),
        ('ABC News', 'https://abcnews.go.com/abcnews/usheadlines'),
    ],
    'GB': [
        ('BBC UK', 'http://feeds.bbci.co.uk/news/uk/rss.xml'),
        ('Guardian UK', 'https://www.theguardian.com/uk/rss'),
        ('Sky News', 'https://feeds.skynews.com/feeds/rss/uk.xml'),
    ],
    'FR': [
        ('France24', 'https://www.france24.com/en/france/rss'),
        ('RFI', 'https://www.rfi.fr/en/rss'),
    ],
    'DE': [
        ('DW', 'https://rss.dw.com/rdf/rss-en-ger'),
    ],
    'UA': [
        ('Kyiv Independent', 'https://kyivindependent.com/feed/'),
        ('Ukrinform', 'https://www.ukrinform.net/rss/block-lastnews'),
    ],
    'RU': [
        ('Moscow Times', 'https://www.themoscowtimes.com/rss/news'),
        ('TASS', 'https://tass.com/rss/v2.xml'),
    ],
    'CN': [
        ('SCMP China', 'https://www.scmp.com/rss/4/feed'),
        ('Xinhua', 'http://www.xinhuanet.com/english/rss/worldrss.xml'),
    ],
    'JP': [
        ('NHK', 'https://www3.nhk.or.jp/nhkworld/rss/world.xml'),
        ('Japan Times', 'https://www.japantimes.co.jp/feed/'),
    ],
    'IN': [
        ('Times of India', 'https://timesofindia.indiatimes.com/rssfeedstopstories.cms'),
        ('NDTV', 'https://feeds.feedburner.com/ndtvnews-latest'),
    ],
    'AU': [
        ('ABC AU', 'https://www.abc.net.au/news/feed/2942460/rss.xml'),
        ('SBS', 'https://www.sbs.com.au/news/feed'),
    ],
    'IL': [
        ('Times of Israel', 'https://www.timesofisrael.com/feed/'),
        ('Haaretz', 'https://www.haaretz.com/cmlink/1.4483969'),
    ],
    'BR': [
        ('Brazil Reports', 'https://www.thebrazilreports.com/feed/'),
    ],
    'SA': [
        ('Arab News', 'https://www.arabnews.com/rss.xml'),
    ],
    'EG': [
        ('Egypt Independent', 'https://egyptindependent.com/feed/'),
    ],
    'TR': [
        ('Daily Sabah', 'https://www.dailysabah.com/rssFeed/turkey'),
    ],
    'MX': [
        ('Mexico News Daily', 'https://mexiconewsdaily.com/feed/'),
    ],
    'CA': [
        ('CBC', 'https://www.cbc.ca/cmlink/rss-topstories'),
        ('Globe and Mail', 'https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/canada/'),
    ],
    'KR': [
        ('Korea Herald', 'http://www.koreaherald.com/common/rss_xml.php?ct=102'),
    ],
    'PK': [
        ('Dawn', 'https://www.dawn.com/feeds/home'),
    ],
    'NG': [
        ('Punch NG', 'https://punchng.com/feed/'),
    ],
}


def _search_rss_regional(region_name: str, country_code: str, lat: float, lng: float) -> list:
    """Fetch region-specific RSS news feeds."""
    feeds = _COUNTRY_RSS.get(country_code, [])
    if not feeds:
        return []

    results = []
    for name, url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                title = entry.get('title', '')
                if not title:
                    continue
                results.append({
                    'title': title,
                    'link': entry.get('link', ''),
                    'source': name,
                    'published': entry.get('published', ''),
                    'description': re.sub(r'<[^>]+>', '', entry.get('summary', ''))[:200],
                    'image_url': '',
                    'lat': lat,
                    'lon': lng,
                    'risk_score': 0.5,
                    'source_type': 'rss_regional',
                    'country_code': country_code,
                })
        except Exception as e:
            logger.debug(f"RSS {name}: {e}")
    return results


def _reddit_media(post: dict) -> tuple[str, str]:
    """Extract media URL and type from a Reddit post."""
    media_url = ""
    media_type = ""
    thumb = post.get("thumbnail", "")
    if thumb and thumb.startswith("http"):
        media_url = thumb
        media_type = "image"
    if post.get("is_video"):
        rv = (post.get("media") or {}).get("reddit_video", {})
        if rv.get("fallback_url"):
            media_url = rv["fallback_url"]
            media_type = "video"
    return media_url, media_type


def _reddit_post(post: dict, sub: str, media_url: str, media_type: str) -> dict:
    """Build a normalized Reddit post dict."""
    return {
        "id": f"reddit-reg-{post.get('id', '')}",
        "platform": "reddit",
        "subreddit": sub or post.get("subreddit", ""),
        "title": post.get("title", "")[:200],
        "author": post.get("author", ""),
        "url": f"https://reddit.com{post.get('permalink', '')}",
        "media_url": media_url,
        "media_type": media_type,
        "score": post.get("score", 0),
        "comments": post.get("num_comments", 0),
        "created": post.get("created_utc", ""),
        "flair": post.get("link_flair_text", "") or post.get("subreddit", ""),
        "nsfw": post.get("over_18", False),
        "regional": True,
    }


# ---------------------------------------------------------------------------
# Reddit Search — searches Reddit for the region name
# ---------------------------------------------------------------------------
def _search_reddit(terms: list[str]) -> list:
    """Search Reddit for posts about the region — both global search and city subreddits."""
    posts = []
    ua = {"User-Agent": "ShadowLens:regional:v1.0 (research)"}

    # 1. Try the city/region as a subreddit directly (r/nashville, r/paris, r/london, etc.)
    for term in terms[:2]:
        sub_name = re.sub(r'[^a-zA-Z]', '', term.split(',')[0].strip()).lower()
        if len(sub_name) < 3:
            continue
        try:
            resp = requests.get(
                f"https://www.reddit.com/r/{sub_name}/hot.json?limit=25",
                timeout=10, headers=ua
            )
            if resp.status_code == 200:
                for child in resp.json().get("data", {}).get("children", []):
                    post = child.get("data", {})
                    title = post.get("title", "")
                    if len(title) < 10:
                        continue
                    media_url, media_type = _reddit_media(post)
                    posts.append(_reddit_post(post, sub_name, media_url, media_type))
        except Exception:
            pass

    # 2. Search all of Reddit for the region name
    for term in terms[:2]:
        try:
            resp = requests.get(
                f"https://www.reddit.com/search.json?q={quote_plus(term)}&sort=new&limit=25&t=day",
                timeout=10, headers=ua
            )
            if resp.status_code != 200:
                continue
            for child in resp.json().get("data", {}).get("children", []):
                post = child.get("data", {})
                title = post.get("title", "")
                if len(title) < 10:
                    continue
                media_url, media_type = _reddit_media(post)
                posts.append(_reddit_post(post, "", media_url, media_type))
        except Exception:
            continue
    return posts


# ---------------------------------------------------------------------------
# Bluesky Search — searches for region keywords
# ---------------------------------------------------------------------------
def _search_bluesky(terms: list[str]) -> list:
    """Search Bluesky for posts about the region."""
    posts = []
    for term in terms[:2]:
        try:
            resp = requests.get(
                f"https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
                f"?q={quote(term)}&limit=20&sort=latest",
                timeout=10,
                headers={"Accept": "application/json"}
            )
            if resp.status_code != 200:
                continue
            for item in resp.json().get("posts", []):
                record = item.get("record", {})
                text = record.get("text", "")
                if len(text) < 20:
                    continue
                author = item.get("author", {})
                handle = author.get("handle", "")

                media_url = ""
                media_type = ""
                embed = item.get("embed", {})
                if embed.get("$type") == "app.bsky.embed.images#view":
                    images = embed.get("images", [])
                    if images:
                        media_url = images[0].get("fullsize", images[0].get("thumb", ""))
                        media_type = "image"

                uri = item.get("uri", "")
                post_id = uri.split("/")[-1] if uri else ""

                posts.append({
                    "id": f"bsky-reg-{post_id}",
                    "platform": "bluesky",
                    "subreddit": term,
                    "title": text[:200],
                    "author": handle,
                    "url": f"https://bsky.app/profile/{handle}/post/{post_id}" if handle and post_id else "",
                    "media_url": media_url,
                    "media_type": media_type,
                    "score": item.get("likeCount", 0),
                    "comments": item.get("replyCount", 0),
                    "created": record.get("createdAt", ""),
                    "flair": "bluesky",
                    "nsfw": False,
                    "regional": True,
                })
        except Exception:
            continue
    return posts


# ---------------------------------------------------------------------------
# Mastodon Search — searches for region keywords across instances
# ---------------------------------------------------------------------------
def _search_mastodon(terms: list[str]) -> list:
    """Search Mastodon for posts about the region."""
    instances = ["mastodon.social", "masto.ai", "mastodon.world"]
    posts = []

    for instance in instances[:2]:
        for term in terms[:2]:
            try:
                tag = re.sub(r'[^a-zA-Z0-9]', '', term).lower()
                if not tag:
                    continue
                resp = requests.get(
                    f"https://{instance}/api/v1/timelines/tag/{tag}?limit=15",
                    timeout=8,
                    headers={"Accept": "application/json"}
                )
                if resp.status_code != 200:
                    continue
                for toot in resp.json():
                    content = toot.get("content", "")
                    text = re.sub(r'<[^>]+>', '', content)
                    if len(text) < 20:
                        continue

                    media_url = ""
                    media_type = ""
                    attachments = toot.get("media_attachments", [])
                    if attachments:
                        media_url = attachments[0].get("url", "")
                        media_type = attachments[0].get("type", "image")

                    acct = toot.get("account", {})
                    posts.append({
                        "id": f"masto-reg-{toot.get('id', '')}",
                        "platform": "mastodon",
                        "subreddit": f"{instance}",
                        "title": text[:200],
                        "author": acct.get("acct", ""),
                        "url": toot.get("url", ""),
                        "media_url": media_url,
                        "media_type": media_type,
                        "score": toot.get("favourites_count", 0),
                        "comments": toot.get("replies_count", 0),
                        "created": toot.get("created_at", ""),
                        "flair": "mastodon",
                        "nsfw": toot.get("sensitive", False),
                        "regional": True,
                    })
            except Exception:
                continue
    return posts


def _search_telegram(terms: list[str]) -> list:
    """Search OSINT Telegram channels for posts about the region."""
    try:
        from services.osint_bridge import telegram_search
        query = " ".join(terms[:2])
        result = telegram_search(query)
        if not isinstance(result, dict) or result.get("status") != "ok":
            return []
        posts = []
        for p in result.get("posts", []):
            content = p.get("content", "")
            if not content or len(content) < 20:
                continue
            posts.append({
                "id": f"tg-reg-{p.get('url', '').split('/')[-1]}",
                "platform": "telegram",
                "subreddit": p.get("channel", ""),
                "title": content[:200],
                "author": p.get("channel", ""),
                "url": p.get("url", ""),
                "media_url": "",
                "media_type": "",
                "score": 0,
                "comments": 0,
                "created": p.get("date", ""),
                "flair": "telegram",
                "nsfw": False,
                "regional": True,
            })
        return posts
    except Exception as e:
        logger.debug(f"Telegram regional search failed: {e}")
        return []
