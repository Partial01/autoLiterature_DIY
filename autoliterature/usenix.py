"""Read bibliographic metadata published on official USENIX presentation pages."""
import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import requests

logger = logging.getLogger(__name__)


def is_usenix_url(value):
    parsed = urlparse(value)
    return (parsed.scheme == "https" and parsed.netloc in ("www.usenix.org", "usenix.org")
            and re.fullmatch(r"/conference/[\w-]+/presentation/[\w-]+/?", parsed.path)
            is not None)


def get_usenix_info(url, proxy=None):
    if not is_usenix_url(url):
        return None
    proxies = None
    if proxy:
        if not proxy.startswith(("http://", "https://")):
            proxy = "http://" + proxy
        proxies = {"http": proxy, "https": proxy}
    try:
        response = requests.get(url, proxies=proxies, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        def values(name):
            return [tag['content'].strip() for tag in soup.find_all('meta', attrs={'name': name})
                    if tag.get('content', '').strip()]

        def first(name):
            found = values(name)
            return found[0] if found else None

        title = first('citation_title')
        if not title:
            logger.warning("USENIX page has no citation_title: %s", url)
            return None
        return {
            'title': title.replace('{', '').replace('}', ''),
            'author': ' and '.join(values('citation_author')),
            'year': first('citation_publication_date'),
            'journal': first('citation_conference_title'),
            'url': url,
            'pdf_link': first('citation_pdf_url'),
            'doi': first('citation_doi'),
            'cited_count': None,
        }
    except requests.RequestException as exc:
        logger.warning("USENIX lookup failed for %s: %s", url, exc)
        return None
