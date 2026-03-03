"""fetcher – async adapters for NewsAPI, NVD/CVE, and RSS sources."""
from .newsapi_fetcher import fetch as fetch_newsapi
from .nvd_fetcher import fetch as fetch_nvd
from .rss_fetcher import fetch as fetch_rss

__all__ = ["fetch_newsapi", "fetch_nvd", "fetch_rss"]
