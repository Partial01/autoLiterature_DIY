import logging
import requests 
from urllib.request import ProxyHandler
import feedparser
try:
    from urllib import quote
except ImportError:
    from urllib.parse import quote
from unidecode import unidecode

from .crossref import crossrefInfo


logging.basicConfig()
logger = logging.getLogger('arxiv')
logger.setLevel(logging.DEBUG)
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:27.0) Gecko/20100101 Firefox/27.0'}

class arxivInfo(object):
    def __init__(self):
        self.base_url = "http://export.arxiv.org/api/query"

    def _normalize_proxy(self, proxy):
        if not proxy:
            return proxy
        if proxy.startswith("http://") or proxy.startswith("https://"):
            return proxy
        return "http://{}".format(proxy)
    
    def set_proxy_handler(self, proxy):
        """set proxy handler
        
        Aargs: 
            proxy (str): proxy (str): The proxy adress. e.g 127.0.1:1123
            
        Returns:
            A proxy handler object.
        """
        proxy_url = self._normalize_proxy(proxy)
        proxy_handler = ProxyHandler({"http": proxy_url,
                                      "https": proxy_url})
        return proxy_handler
            
    
    def extract_json_info(self, item):
        """Extract bib json information from requests.get().json()
        
        Args:
            item (json object): obtained by requests.get().json()
        
        Returns:
            A dict containing the paper information.
        """
        paper_url = item.link 
        title = item.title
        journal = "arxiv"
        published = item.published.split("-")
        if len(published) > 1:
            year = published[0]
        else: 
            year = ' '

        authors = item.authors
        if len(authors) > 0:
            first_author = authors[0]["name"].split(" ")
            authors = " and ".join([author["name"] for author in authors])
        else:
            first_author = authors
            authors = authors

        bib_dict = {
            "title": title,
            "author": authors,
            "journal": journal,
            "year": year,
            "url": paper_url,
            "arxiv_id": paper_url.rsplit("/", 1)[-1],
            "doi": item.get("arxiv_doi") if hasattr(item, "get") else None,
            "pdf_link": item.link.replace("abs", "pdf")+".pdf",
            "cited_count": None
        }
        
        return bib_dict


    def get_info_by_arxivid(self, arxivId, handler=False):
        """Get the meta information by the given paper arxiv_id. 
        
        Args:
            doi (str): The arxiv Id
            handler (handler object): use proxy
            
        Returns:
            A dict containing the paper information. 
            {
                "title": xxx,
                "author": xxx,
                "journal": xxx,
                etc
            } 
            OR
            None
        """
        
        params = "?search_query=id:"+quote(unidecode(arxivId))
        
        max_attempts = 2
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                if handler:
                    result = feedparser.parse(self.base_url + params, handlers=[handler])
                else:
                    result = feedparser.parse(self.base_url + params)

                items = result.entries
                if not items:
                    last_error = getattr(result, "bozo_exception", None)
                    if attempt < max_attempts:
                        logger.warning("arXiv lookup returned no entries for {}. Retrying.".format(arxivId))
                    continue

                item = items[0]
                if "arxiv_doi" in item:
                    doi = item["arxiv_doi"]

                    crossref_info = crossrefInfo()
                    if handler:
                        crossref_info.set_proxy(proxy=handler.proxies["http"])
                    crossref_bib = crossref_info.get_info_by_doi(doi)
                    if crossref_bib:
                        crossref_bib["arxiv_id"] = arxivId
                        crossref_bib["arxiv_url"] = item.link
                        if not crossref_bib.get("pdf_link"):
                            crossref_bib["pdf_link"] = item.link.replace("abs", "pdf")+".pdf"
                        return crossref_bib
                    return self.extract_json_info(item)
                else:
                    return self.extract_json_info(item)
            except Exception as exc:
                last_error = exc
                if attempt < max_attempts:
                    logger.warning("arXiv lookup failed for {}. Retrying: {}".format(arxivId, exc))

        if last_error:
            logger.error("No arXiv entries found for {} after {} attempts: {}".format(arxivId, max_attempts, last_error))
        else:
            logger.error("No arXiv entries found for {} after {} attempts.".format(arxivId, max_attempts))
        return None
            
    
    def get_info_by_title(self, title, field='ti'):
        """Get the meta information by the given paper title. 
        
        Args:
            doi (str): The paper title
            
        Returns:
            A dict containing the paper information. 
            {
                "title": xxx,
                "author": xxx,
                "journal": xxx,
                etc
            }
            OR
            None
            OR
            A list [{}, {}, {}]
        """
        params = "?search_query="+field+":"+quote(unidecode(title))
        url = self.base_url + params
        try:
            result = feedparser.parse(url)
            items = result.entries
            print(len(items))
            
            for i, item in enumerate(items):
                
                title_item = item.title
                try:
                    title_item = title_item.decode("utf-8")
                except:
                    pass
            
                item.title = title_item

                if title_item.lower() == title.lower():
                    return self.extract_json_info(item)
                
                items[i] = item

            return [self.extract_json_info(it) for it in items]
        except:
            logger.error("Title: {} is error.".format(title)) 
            
            
if __name__ == "__main__":
    arxivId = "2208.05623"
    title = "Heterogeneous Graph Attention Network"
    
    arxiv_info = arxivInfo()
    arxiv_info.set_proxy_handler(proxy="127.0.1:1123")
    
    bib_arxiv = arxiv_info.get_info_by_arxivid(arxivId)
    # bib_title = arxiv_info.get_info_by_title(title)
    
    print(bib_arxiv)
    print("\n")
    # print(bib_title)
