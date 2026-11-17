import logging
import requests 
from urllib.parse import quote
# 
# 1. get info by doi
# 2. get info by title

logging.basicConfig()
logger = logging.getLogger('crossref')
logger.setLevel(logging.DEBUG)
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:27.0) Gecko/20100101 Firefox/27.0'}

class crossrefInfo(object):
    def __init__(self):
        self.sess = requests.Session()
        self.sess.headers = HEADERS
        self.base_url = "https://api.crossref.org/"

    def set_proxy(self, proxy=None):
        """set proxy for session
        
        Args:
            proxy (str): The proxy adress. e.g 127.0.1:1123
        Returns:
            None
        """
        if proxy:
            if not proxy.startswith(("http://", "https://")):
                proxy = "http://" + proxy
            self.sess.proxies = {
                "http": proxy,
                "https": proxy, }
            
    
    def extract_json_info(self, bib):
        """Extract bib json information from requests.get().json()
        
        Args:
            bib (json object): obtained by requests.get().json()
        
        Returns:
            A dict containing the paper information.
        """
        title = next((title for title in bib.get('title', []) if title.strip()), None)
        if not title:
            raise ValueError("Crossref record has no title")
        pub_date = None
        for field in ('published', 'published-print', 'published-online', 'issued'):
            date_parts = (bib.get(field) or {}).get('date-parts') or []
            if date_parts and date_parts[0]:
                pub_date = '-'.join(str(i) for i in date_parts[0])
                break

        if bib.get('author'):
            authors = ' and '.join(
                ["{} {}".format(i.get("given", ""), i.get("family", "")).strip() for i in bib['author']]
            )
        else:
            authors = "No author"

        short_container_title = bib.get('short-container-title') or []
        container_title = bib.get('container-title') or []

        if short_container_title:
            journal = short_container_title[0]
        elif container_title:
            journal = container_title[0]
        else:
            journal = "No journal"

        pdf_link = None
        links = bib.get("link") or []
        if links:
            pdf_link = next((link.get("URL") for link in links
                             if link.get("content-type") == "application/pdf"), None)

        bib_dict = {
            "title": title,
            "author": authors,
            "journal": journal,
            "short_container_title": short_container_title,
            "container_title": container_title,
            "year": pub_date,
            "url": bib.get("URL") or "https://doi.org/{}".format(bib.get("DOI", "")),
            "doi": bib.get("DOI"),
            "pdf_link": pdf_link,
            "cited_count": bib.get("is-referenced-by-count")
        } 
        
        return bib_dict


    def get_info_by_doi(self, doi):
        """Get the meta information by the given paper DOI number. 
        
        Args:
            doi (str): The paper DOI number
            
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
        data = self._request_json("works/" + quote(doi, safe="/"), doi)
        if data is not None:
            try:
                return self.extract_json_info(data['message'])
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                logger.error("Crossref metadata invalid for %s: %s", doi, exc)
        return None

    def _request_json(self, path, target, params=None):
        try:
            response = self.sess.get(self.base_url + path, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            logger.warning("Crossref HTTP %s for %s", status, target)
            if status == 404 and target.startswith("10.5555/"):
                logger.warning(
                    "10.5555 is a test/unmaintained prefix; an ACM catalog entry does not "
                    "guarantee a registered DOI. Use the official USENIX presentation URL "
                    "or an arXiv ID instead. The original placeholder is preserved."
                )
        except requests.Timeout:
            logger.warning("Crossref timeout for %s", target)
        except requests.RequestException as exc:
            logger.warning("Crossref network error for %s: %s", target, exc)
        except ValueError as exc:
            logger.warning("Crossref invalid JSON for %s: %s", target, exc)
        return None
            
    
    def get_info_by_title(self, title):
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
        params = {"query.bibliographic": title, "rows": 20}
        data = self._request_json("works", title, params=params)
        if data is None:
            return None
        try:
            items = data["message"]["items"]
            
            for i, item in enumerate(items):
                
                title_item = item['title'][0]
                try:
                    title_item = title_item.decode("utf-8")
                except:
                    pass
            
                item["title"][0] = title_item

                if title_item.lower() == title.lower():
                    return self.extract_json_info(item)
                
                items[i] = item

            return [self.extract_json_info(it) for it in items]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            logger.error("Crossref metadata invalid for title %s: %s", title, exc)
            
            
if __name__ == "__main__":
    # doi = "10.1016/j.wneu.2012.11.074"
    # doi = "10.1093/cercor/bhac266"
    doi = "10.1038/s41467-022-29269-6"
    # title = "Heterogeneous Graph Attention Network"
    # title = "Learning to Copy Coherent Knowledge for Response Generation"
    
    crossref_info = crossrefInfo()
    crossref_info.set_proxy(proxy="127.0.1:1123")
    
    bib_doi = crossref_info.get_info_by_doi(doi)
    # bib_title = crossref_info.get_info_by_title(title)
    
    print(bib_doi)
    print("\n")
    # print(bib_title)
