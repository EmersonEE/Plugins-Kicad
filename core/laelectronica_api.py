"""API client and search engine for laelectronica.com.gt (Guatemala)."""

import json
import re
import ssl
import urllib.parse
import urllib.request
from typing import Callable, Dict, List, Optional, Tuple

from core.bom_extractor import BOMItem, ProductMatch


class LaElectronicaClient:
    """Client for querying products and live prices from laelectronica.com.gt."""

    BASE_URL = "https://laelectronica.com.gt"
    SEARCH_ENDPOINT = "https://laelectronica.com.gt/search/suggest.json"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.cache: Dict[str, List[ProductMatch]] = {}
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE

    def search_products(self, query: str) -> List[ProductMatch]:
        """Search products on laelectronica.com.gt for a given keyword."""
        q = query.strip()
        if not q:
            return []

        if q in self.cache:
            return self.cache[q]

        params = {
            "q": q,
            "resources[type]": "product",
            "resources[options][fields]": "title,body,product_type,variants.title,vendor",
        }
        url = f"{self.SEARCH_ENDPOINT}?{urllib.parse.urlencode(params)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "es-GT,es;q=0.9,en;q=0.8",
        }

        req = urllib.request.Request(url, headers=headers)
        matches = []

        try:
            with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                products = (
                    data.get("resources", {})
                    .get("results", {})
                    .get("products", [])
                )

                for p in products:
                    title = p.get("title", "")
                    raw_price = str(p.get("price", "0")).replace(",", "")
                    try:
                        price = float(raw_price)
                    except ValueError:
                        price = 0.0

                    available = p.get("available", True)
                    prod_url = p.get("url", "")
                    img_url = p.get("image", "") or p.get("featured_image", {}).get("url", "")
                    handle = p.get("handle", "")

                    matches.append(
                        ProductMatch(
                            title=title,
                            price=price,
                            price_str=f"Q{price:.2f}",
                            available=available,
                            url=prod_url,
                            image_url=img_url,
                            handle=handle,
                        )
                    )
        except Exception:
            pass

        self.cache[q] = matches
        return matches

    def find_best_match(
        self, queries: List[str]
    ) -> Tuple[Optional[ProductMatch], List[ProductMatch]]:
        """Try a list of fallback queries and return (best_match, all_candidates)."""
        all_candidates: List[ProductMatch] = []
        seen_urls = set()

        for q in queries:
            results = self.search_products(q)
            for item in results:
                if item.url not in seen_urls:
                    seen_urls.add(item.url)
                    all_candidates.append(item)

            if results and not all_candidates:
                all_candidates = results

        best_match = all_candidates[0] if all_candidates else None
        return best_match, all_candidates

    def match_bom_items(
        self,
        items: List[BOMItem],
        on_progress: Optional[Callable[[int, int, BOMItem], None]] = None,
    ):
        """Perform batch online lookup for all BOM items."""
        total = len(items)
        for idx, item in enumerate(items, 1):
            if item.ignored:
                if on_progress:
                    on_progress(idx, total, item)
                continue

            queries = item.generate_search_queries()
            best, candidates = self.find_best_match(queries)
            item.matched_product = best

            if on_progress:
                on_progress(idx, total, item)
