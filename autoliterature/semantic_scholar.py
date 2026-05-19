import logging
import os
import threading
import time

import requests


logging.basicConfig()
logger = logging.getLogger('semantic_scholar')
logger.setLevel(logging.INFO)

FIELDS = "title,year,venue,url,citationCount,openAccessPdf,authors"
BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/{}"
SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:27.0) Gecko/20100101 Firefox/27.0'}
MIN_REQUEST_INTERVAL_SECONDS = 1.0
_rate_limit_lock = threading.Lock()
_last_request_time = None
_rate_limit_warning_logged = False


def _paper_key(doi=None, arxiv_id=None):
    if doi:
        return "DOI:{}".format(doi)
    if arxiv_id:
        return "ARXIV:{}".format(arxiv_id)
    return None


def _normalize_title(title):
    if not title:
        return None
    return " ".join(str(title).split()).lower()


def _throttle_request():
    global _last_request_time
    with _rate_limit_lock:
        now = time.monotonic()
        if _last_request_time is not None:
            elapsed = now - _last_request_time
            wait_seconds = MIN_REQUEST_INTERVAL_SECONDS - elapsed
            if wait_seconds > 0:
                time.sleep(wait_seconds)
                now += wait_seconds
        _last_request_time = now


def _request_json(sess, url, params, headers, paper_key=None):
    global _rate_limit_warning_logged
    try:
        _throttle_request()
        response = sess.get(
            url,
            params=params,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            return data
    except requests.exceptions.HTTPError as exc:
        response = getattr(exc, "response", None)
        target = paper_key or url
        if response is not None and response.status_code == 429:
            if not _rate_limit_warning_logged:
                logger.warning(
                    "Semantic Scholar 已触发官方限流，本次使用基础信息继续。可设置 SEMANTIC_SCHOLAR_API_KEY 后使用 --semantic-scholar。"
                )
                _rate_limit_warning_logged = True
        else:
            logger.debug("Semantic Scholar lookup failed for {}: {}".format(target, exc))
    except Exception as exc:
        target = paper_key or url
        logger.debug("Semantic Scholar lookup failed for {}: {}".format(target, exc))
    return {}


def _select_title_match(search_data, title):
    papers = search_data.get("data") or []
    normalized_title = _normalize_title(title)
    for paper in papers:
        if _normalize_title(paper.get("title")) == normalized_title:
            return paper
    return {}


def get_semantic_scholar_info(doi=None, arxiv_id=None, title=None, proxy=None):
    """Fetch Semantic Scholar metadata by DOI/arXiv id, then exact title fallback."""
    sess = requests.Session()
    sess.headers = HEADERS
    if proxy:
        sess.proxies = {"http": proxy, "https": proxy}

    headers = {}
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key

    paper_key = _paper_key(doi=doi, arxiv_id=arxiv_id)
    if paper_key:
        data = _request_json(
            sess,
            BASE_URL.format(paper_key),
            params={"fields": FIELDS},
            headers=headers,
            paper_key=paper_key,
        )
        if data:
            return data

    if title:
        search_data = _request_json(
            sess,
            SEARCH_URL,
            params={"query": title, "limit": 5, "fields": FIELDS},
            headers=headers,
            paper_key=title,
        )
        return _select_title_match(search_data, title)

    return {}
