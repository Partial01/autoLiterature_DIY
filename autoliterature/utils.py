import os 
import logging
import re 
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm 
from .citations import citation_value, metadata_comment, tracking_metadata
from .downloads import (
    enrich_paper_info_with_semantic_scholar,
    get_paper_info_from_paperid,
    get_paper_pdf_from_paperid,
)

logging.basicConfig()
logger = logging.getLogger('utils')
logger.setLevel(logging.INFO)

LINKS = ["pdf", "arxiv", "s2"]

VENUE_ALIASES = { # TODO: expand this dict
    "Neural Information Processing Systems": "NeurIPS",
    "neurips": "NeurIPS",
    "Computer Vision and Pattern Recognition": "CVPR",
    "cvpr": "CVPR",
    "international conference on computer vision": "ICCV",
    "iccv": "ICCV",
    "european conference on computer vision": "ECCV",
    "eccv": "ECCV",
    "international conference on machine learning": "ICML",
    "icml": "ICML",
    "international conference on learning representations": "ICLR",
    "iclr": "ICLR",
    "association for computational linguistics": "ACL",
    "acl": "ACL",
    "empirical methods in natural language processing": "EMNLP",
    "emnlp": "EMNLP",
    "aaai": "AAAI",
    "ijcai": "IJCAI",
}


class patternRecognizer(object):
    def __init__(self, regular_rule):
        self.pattern = re.compile(regular_rule)

    def match(self, string):
        return self.pattern.match(string)
    
    def findall(self, string):
        return self.pattern.findall(string)

    def multiple_replace(self, content, **replace_dict):
        def replace_(value):
            match = value.group()
            if match in replace_dict.keys():
                return replace_dict[match]
            else:
                return match
        
        replace_content = self.pattern.sub(replace_, content)
        
        return replace_content
    

def note_modified(pattern_recog, md_file, **replace_dict):
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    replaced_content = pattern_recog.multiple_replace(content, **replace_dict)

    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(''.join(replaced_content))
        
 
def get_pdf_paths(pdf_root):
    pdf_paths = []
    for root, _, files in os.walk(pdf_root):
        for file in files:
            if file.lower().endswith('.pdf'):
                pdf_paths.append(os.path.join(root, file))
                
    return pdf_paths
 
        
def get_pdf_paths_from_notes(md_root, reg):
    
    md_files = []
    for root, _, files in os.walk(md_root):
        for file in files:
            if file.lower().endswith('md') or file.lower().endswith('markdown'):
                md_files.append(os.path.join(root, file))
    
    pdf_paths_from_notes = []
    for md_file in md_files:
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
        m = reg.findall(content)
        m = [i.split("(")[-1].split(')')[0] for i in m]
        pdf_paths_from_notes.extend(m)

    return pdf_paths_from_notes


def get_pdf_paths_from_notes_dict(md_root, reg):
    pdf_paths_from_notes_dict = {}
    if os.path.isdir(md_root):
        md_files = []
        for root, _, files in os.walk(md_root):
            for file in files:
                if file.lower().endswith('md') or file.lower().endswith('markdown'):
                    md_files.append(os.path.join(root, file))
    
        for md_file in md_files:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            m = reg.findall(content)
            m = [i.split("(")[-1].split(')')[0] for i in m]
            pdf_paths_from_notes_dict[md_file] = m
    else:
        with open(md_root, 'r', encoding='utf-8') as f:
            content = f.read()
        m = reg.findall(content)
        m = [i.split("(")[-1].split(')')[0] for i in m]
        pdf_paths_from_notes_dict[md_root] = m
            
    return pdf_paths_from_notes_dict


def classify_identifier(identifier):
    """Not need to download PDF file 
    """
    if identifier.endswith("}}"):
        return True 
    else: 
        return False 


def _first(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _clean_value(value):
    value = _first(value)
    if value is None:
        return None
    value = str(value).strip()
    if not value or value.lower() in ["no journal", "none"]:
        return None
    return value


def _alias_venue(venue):
    if not venue:
        return None
    venue_lower = venue.lower()
    for key, alias in VENUE_ALIASES.items():
        if key.lower() in venue_lower:
            return alias
    return venue


def _select_venue(bib):
    s2 = bib.get("semantic_scholar") or {}
    venue = (
        _clean_value(bib.get("short_container_title"))
        or _clean_value(bib.get("container_title"))
        or _clean_value(s2.get("venue"))
        or _clean_value(bib.get("journal"))
    )
    return _alias_venue(venue)


def _first_author(bib):
    authors = bib.get("author")
    if authors:
        first = str(authors).split(" and ")[0].strip()
        if " and " in str(authors):
            return "{} et al.".format(first)
        return first

    s2_authors = (bib.get("semantic_scholar") or {}).get("authors") or []
    if s2_authors:
        first = s2_authors[0].get("name", "").strip()
        if len(s2_authors) > 1:
            return "{} et al.".format(first)
        return first
    return "No author"


def _citation_count(bib):
    return citation_value(bib)[0]


def _semantic_scholar_pdf_url(bib):
    pdf = (bib.get("semantic_scholar") or {}).get("openAccessPdf") or {}
    return pdf.get("url") if isinstance(pdf, dict) else None


def _arxiv_url(bib):
    if bib.get("arxiv_url"):
        return bib.get("arxiv_url")
    url = bib.get("url")
    if url and "arxiv.org/abs/" in url:
        return url
    pdf_link = bib.get("pdf_link") or _semantic_scholar_pdf_url(bib)
    if pdf_link and "arxiv.org/pdf/" in pdf_link:
        return pdf_link.replace("/pdf/", "/abs/").replace(".pdf", "")
    return None


def _doi_url(bib):
    doi = bib.get("doi")
    if doi:
        return "https://doi.org/{}".format(doi)
    url = bib.get("url")
    if url and "doi.org" in url:
        return url
    return None


def _local_pdf_url(pdf_path, note_file):
    if not pdf_path:
        return None
    if note_file:
        note_dir = os.path.dirname(os.path.abspath(note_file))
        rel_path = os.path.relpath(pdf_path, note_dir)
    else:
        rel_path = pdf_path
    return rel_path.replace("\\", "/")


def _pdf_url(bib, pdf_path=None, note_file=None):
    return (
        _local_pdf_url(pdf_path, note_file)
        or bib.get("pdf_link")
        or _semantic_scholar_pdf_url(bib)
    )


def _link_url(kind, bib, pdf_path=None, note_file=None):
    s2 = bib.get("semantic_scholar") or {}
    if kind == "pdf":
        return _pdf_url(bib, pdf_path=pdf_path, note_file=note_file)
    if kind == "arxiv":
        return _arxiv_url(bib)
    if kind == "doi":
        return _doi_url(bib)
    if kind == "s2":
        return s2.get("url")
    if kind == "link":
        return bib.get("url")
    return None


def format_literature_entry(bib, pdf_path=None, note_file=None, paper_id=None):
    title = bib.get("title", "No title")
    author = _first_author(bib)
    venue = _select_venue(bib)
    year = _clean_value(bib.get("year"))

    venue_year = ""
    if venue and year:
        venue_year = " {}, {}".format(venue, year)
    elif venue:
        venue_year = " {}".format(venue)
    elif year:
        venue_year = " {}".format(year)

    links = []
    for kind in LINKS:
        url = _link_url(kind, bib, pdf_path=pdf_path, note_file=note_file)
        if url:
            label = "arXiv" if kind == "arxiv" else kind.upper()
            if kind == "s2":
                label = "S2"
            links.append("([{}]({}))".format(label, url))

    citations = _citation_count(bib)
    citation_text = ""
    if citations is not None:
        citation_text = " (Citations {})".format(citations)

    suffix = ""
    if links:
        suffix += " " + " ".join(links)
    suffix += citation_text
    if paper_id:
        suffix += " " + metadata_comment(tracking_metadata(bib, paper_id))

    return "- **{}**. *{}*{}{}\n\t- ".format(title, author, venue_year, suffix)


def get_update_content(m, note_file, pdfs_path, proxy, semantic_scholar=False):
    
    replace_dict = dict()
    pending_entries = []
    with ThreadPoolExecutor(max_workers=1) as semantic_executor:
        for literature in tqdm(m):
            pdf = classify_identifier(literature)
        
            literature_id = literature.split('{')[-1].split('}')[0].strip()
            bib = get_paper_info_from_paperid(
                literature_id,
                proxy=proxy,
                enrich_semantic=False,
            )
            if not bib:
                logger.info("No metadata found; skipping %s", literature_id)
                continue
        
            try:
                pdf_name = '_'.join(bib.get('title', literature_id).split(' ')) + '.pdf'
                # rep specific symbol with '_'
                pdf_name = re.sub(r"[<>:\"/\\|?*\n\r\x00-\x1F\x7F']", '_', pdf_name)
                pdf_path = os.path.join(pdfs_path, pdf_name)
            
                if pdf:
                    if not os.path.exists(pdf_path):
                        get_paper_pdf_from_paperid(literature_id, pdf_path, direct_url=bib.get('pdf_link'), proxy=proxy)
                        if not os.path.exists(pdf_path):
                            get_paper_pdf_from_paperid(literature_id, pdf_path, proxy=proxy)

                local_pdf_path = pdf_path if os.path.exists(pdf_path) else None
                if semantic_scholar:
                    semantic_future = semantic_executor.submit(
                        enrich_paper_info_with_semantic_scholar,
                        bib,
                        literature_id,
                        proxy=proxy,
                    )
                    pending_entries.append((literature, literature_id, local_pdf_path, bib, semantic_future))
                else:
                    replace_dict[literature] = format_literature_entry(
                        bib,
                        pdf_path=local_pdf_path,
                        note_file=note_file,
                        paper_id=literature_id,
                    )
            except Exception as exc:
                logger.info("Paper download failed; skipping %s: %s", literature_id, type(exc).__name__)
        
        for literature, literature_id, local_pdf_path, bib, semantic_future in pending_entries:
            try:
                enriched_bib = semantic_future.result()
                if enriched_bib:
                    bib = enriched_bib
                replace_dict[literature] = format_literature_entry(
                    bib,
                    pdf_path=local_pdf_path,
                    note_file=note_file,
                    paper_id=literature_id,
                )
            except Exception as exc:
                logger.info("Semantic Scholar enrichment failed; using base metadata for %s: %s", literature_id, type(exc).__name__)
                replace_dict[literature] = format_literature_entry(
                    bib,
                    pdf_path=local_pdf_path,
                    note_file=note_file,
                    paper_id=literature_id,
                )

    return replace_dict
