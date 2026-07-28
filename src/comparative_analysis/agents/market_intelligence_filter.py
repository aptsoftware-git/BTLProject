from __future__ import annotations

import logging
import re
from typing import List, Dict, Set
from urllib.parse import urlparse

from src.comparative_analysis.models import TavilySearchResult, CompetitorRawData

logger = logging.getLogger("comparative_analysis.market_intelligence_filter")

# Domain & URL patterns to exclude (directory lists, review portals, news, wikipedia, listicle aggregators)
NOISE_DOMAINS = {
    "wikipedia.org", "en.wikipedia.org", "medium.com", "wordpress.com", "blogspot.com",
    "reuters.com", "bloomberg.com", "news.google.com", "cnbc.com", "forbes.com",
    "linkedin.com", "naukri.com", "glassdoor.com", "indeed.com", "businessinsider.com",
    "crunchbase.com", "pitchbook.com", "youtube.com", "facebook.com", "techcrunch.com",
    "twitter.com", "x.com", "instagram.com", "reddit.com", "quora.com", "yahoo.com",
    "scribd.com", "slideshare.net", "github.com", "clutch.co", "g2.com", "capterra.com",
    "trustpilot.com", "goodfirms.co", "upcity.com", "softwareadvice.com", "top50.com",
    "top10.com", "cbinsights.com", "getlatka.com", "latka.com", "zoominfo.com",
    "dnb.com", "owler.com", "rocketreach.co", "craft.co"
}

NOISE_PATH_KEYWORDS = [
    "/blog/", "/blogs/", "/news/", "/article/", "/press-release/", "/press/",
    "/careers/", "/jobs/", "/job/", "/vacancy/", ".pdf", "/pdf/", "/top-",
    "/best-", "/list-", "/directory/", "/ranking/", "/comparison/", "/vs/", "/reviews/"
]


class MarketIntelligenceFilter:
    """
    Market Intelligence Filter Agent.
    Filters out noise URLs (Wikipedia, review portals, ranking listicles, blogs, job boards, CB Insights, GetLatka),
    and groups clean search snippets by genuine candidate company / official domain.
    """

    def __init__(self, top_k_companies: int = 5) -> None:
        self.top_k_companies = top_k_companies

    def filter_and_group(
        self,
        search_results: List[TavilySearchResult],
        target_company_name: str
    ) -> List[CompetitorRawData]:
        logger.info("Filtering %d Tavily search snippets...", len(search_results))

        company_map: Dict[str, CompetitorRawData] = {}
        target_name_lower = target_company_name.lower().strip()

        for item in search_results:
            url = item.url.strip()
            if not url or self._is_noise_url(url):
                logger.debug("Skipping noise URL: %s", url)
                continue

            clean_domain = item.website or self._extract_domain(url)
            comp_name = item.company_name or self._extract_company_name_from_domain(clean_domain)

            if self._is_target_company(comp_name, target_name_lower):
                logger.debug("Skipping target company self-match: %s", comp_name)
                continue

            comp_key = self._normalize_key(comp_name, clean_domain)

            if comp_key not in company_map:
                company_map[comp_key] = CompetitorRawData(
                    competitor_name=comp_name,
                    official_website=clean_domain,
                    search_results=[item],
                    source_urls=[url]
                )
            else:
                existing = company_map[comp_key]
                existing.search_results.append(item)
                if url not in existing.source_urls:
                    existing.source_urls.append(url)

        sorted_companies = list(company_map.values())
        sorted_companies.sort(
            key=lambda c: max((s.score for s in c.search_results), default=0.0),
            reverse=True
        )

        filtered_top_5 = sorted_companies[:self.top_k_companies]

        logger.info(
            "MarketIntelligenceFilter returned %d verified competitor candidates.",
            len(filtered_top_5)
        )

        return filtered_top_5

    def _is_noise_url(self, url: str) -> bool:
        url_lower = url.lower()
        if url_lower.endswith(".pdf"):
            return True

        try:
            parsed = urlparse(url_lower)
            domain = parsed.netloc.replace("www.", "")

            if domain in NOISE_DOMAINS or any(nd in domain for nd in ["wikipedia", "naukri", "glassdoor", "indeed", "linkedin", "top50", "clutch", "cbinsights", "latka", "zoominfo"]):
                return True

            path = parsed.path
            if any(keyword in path for keyword in NOISE_PATH_KEYWORDS):
                return True

        except Exception:
            pass

        return False

    def _is_target_company(self, company_name: str, target_name_lower: str) -> bool:
        comp_lower = company_name.lower().strip()
        if comp_lower in target_name_lower or target_name_lower in comp_lower:
            return True
        target_tokens = set(re.findall(r"\w+", target_name_lower)) - {"ltd", "inc", "corp", "co", "llc", "epc", "solutions", "limited"}
        comp_tokens = set(re.findall(r"\w+", comp_lower)) - {"ltd", "inc", "corp", "co", "llc", "epc", "solutions", "limited"}
        if target_tokens and comp_tokens and (target_tokens == comp_tokens or (len(target_tokens) >= 2 and target_tokens.issubset(comp_tokens))):
            return True
        return False

    def _normalize_key(self, company_name: str, domain: str) -> str:
        try:
            parsed = urlparse(domain)
            dom_name = parsed.netloc.replace("www.", "").split(".")[0]
            if dom_name and len(dom_name) > 3:
                return dom_name.lower()
        except Exception:
            pass

        clean = re.sub(r"[^\w\s]", "", company_name.lower())
        tokens = [t for t in clean.split() if t not in {"ltd", "limited", "inc", "corp", "co", "llc", "epc", "solutions", "group"}]
        return "_".join(tokens) if tokens else company_name.lower().strip()

    def _extract_domain(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            scheme = parsed.scheme or "https"
            netloc = parsed.netloc or parsed.path.split('/')[0]
            return f"{scheme}://{netloc}"
        except Exception:
            return url

    def _extract_company_name_from_domain(self, domain: str) -> str:
        try:
            parsed = urlparse(domain)
            dom_name = parsed.netloc.replace("www.", "").split(".")[0]
            return dom_name.capitalize()
        except Exception:
            return "Enterprise Peer"
