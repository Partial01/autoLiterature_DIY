"""Track paper identities and refresh citation counts without rewriting notes."""
from datetime import datetime, timezone
import json
import logging
import os
import re
import tempfile
from urllib.parse import unquote, urlparse

from .crossref import crossrefInfo
from .semantic_scholar import get_semantic_scholar_info
from .usenix import is_usenix_url

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
MARKER = re.compile(r'<!-- autoliter: (.*?) -->')
ENTRY = re.compile(r'^\s*- \*\*(.+?)\*\*\.')
COUNT = re.compile(r'\(Citations \d+\)')
URL = re.compile(r'\]\((https?://[^\s)]+)\)')


def valid_count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def citation_value(bib):
    s2_count = (bib.get('semantic_scholar') or {}).get('citationCount')
    if valid_count(s2_count):
        return s2_count, 'semantic_scholar'
    count = bib.get('cited_count')
    if valid_count(count):
        return count, 'crossref'
    return None, None


def _checked_at():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _s2_id(url):
    if not url:
        return None
    parsed = urlparse(url)
    candidate = parsed.path.rstrip('/').rsplit('/', 1)[-1]
    if (parsed.hostname in ('www.semanticscholar.org', 'semanticscholar.org')
            and parsed.path.startswith('/paper/')
            and re.fullmatch(r'[a-fA-F0-9]{40}', candidate)):
        return candidate
    return None


def tracking_metadata(bib, paper_id):
    s2 = bib.get('semantic_scholar') or {}
    meta = {'v': 1, 'id': paper_id}
    if re.fullmatch(r'10\.\d{4,9}/\S+', paper_id):
        meta['doi'] = paper_id
    elif re.fullmatch(r'(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?', paper_id):
        meta['arxiv_id'] = paper_id
    for key, value in (
        ('doi', bib.get('doi')),
        ('arxiv_id', bib.get('arxiv_id')),
        ('s2_id', s2.get('paperId') or _s2_id(s2.get('url'))),
        ('url', bib.get('url')),
    ):
        if value:
            meta[key] = value
    count, source = citation_value(bib)
    if source:
        meta.update(citation_count=count, citation_source=source, citation_checked_at=_checked_at())
    return meta


def metadata_comment(meta):
    # Prevent a title/identifier containing HTML comment syntax from ending the comment.
    data = json.dumps(meta, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e')
    return '<!-- autoliter: {} -->'.format(data)


def _legacy_identity(line):
    meta = {'v': 1}
    identities = {}

    def remember(key, value):
        identities.setdefault(key, set()).add(value)
        meta[key] = value

    for url in URL.findall(line):
        parsed = urlparse(unquote(url))
        host = parsed.hostname
        path = parsed.path
        s2 = _s2_id(url)
        if s2:
            remember('s2_id', s2)
        if host in ('doi.org', 'dx.doi.org'):
            candidate = path.lstrip('/')
        elif host == 'dl.acm.org':
            candidate = re.sub(r'^/doi/(?:(?:abs|full|pdf|epdf)/)?', '', path)
        else:
            candidate = ''
        if re.fullmatch(r'10\.\d{4,9}/\S+', candidate):
            remember('doi', candidate)
        if host in ('arxiv.org', 'www.arxiv.org'):
            match = re.fullmatch(r'/(?:abs|pdf)/(.+?)(?:\.pdf)?', path)
            if match:
                remember('arxiv_id', match[1])
        if is_usenix_url(url):
            remember('url', url)
    if any(len(values) > 1 for values in identities.values()):
        return {}
    if meta.get('s2_id'):
        meta['citation_source'] = 'semantic_scholar'
        meta['id'] = meta['s2_id']
    elif meta.get('doi'):
        meta['citation_source'] = 'crossref'
        meta['id'] = meta['doi']
    elif meta.get('arxiv_id'):
        meta['citation_source'] = 'semantic_scholar'
        meta['id'] = meta['arxiv_id']
    elif meta.get('url'):
        meta['id'] = meta['url']
    return meta


def _lookup(meta, title, proxy, semantic_scholar):
    source = meta.get('citation_source')
    if source is None:
        source = 'crossref' if meta.get('doi') else 'semantic_scholar'
    if source == 'crossref':
        doi = meta.get('doi')
        if not doi:
            return None
        client = crossrefInfo()
        client.set_proxy(proxy)
        bib = client.get_info_by_doi(doi)
        count = (bib or {}).get('cited_count')
        if valid_count(count):
            return count, source, None
    elif source == 'semantic_scholar':
        if not semantic_scholar:
            logger.info("Skipping S2 citation refresh for %s; enable --semantic-scholar", meta.get('id'))
            return None
        arxiv = meta.get('arxiv_id')
        if arxiv:
            arxiv = re.sub(r'v\d+$', '', arxiv)
        kwargs = {'proxy': proxy}
        if meta.get('s2_id'):
            kwargs['paper_id'] = meta['s2_id']
        else:
            kwargs.update(doi=meta.get('doi'), arxiv_id=arxiv)
            if not meta.get('doi') and not arxiv and is_usenix_url(meta.get('url', '')):
                kwargs['title'] = title
        data = get_semantic_scholar_info(**kwargs)
        count = data.get('citationCount')
        if valid_count(count):
            return count, source, data.get('paperId') or _s2_id(data.get('url'))
    return None


def refresh_citations(content, proxy=None, semantic_scholar=False):
    """Update only generated entry citation fields and tracking comments.

    Existing source attribution is binding. Legacy entries infer it from S2/DOI
    links, in that order. No identity, invalid markers, and failed lookups leave
    the entire line unchanged. Cache repeated paper lookups within one note.
    """
    cache = {}
    lines = []
    fence = None
    for line in content.splitlines(keepends=True):
        delimiter = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if delimiter:
            token = delimiter[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            lines.append(line)
            continue
        entry = ENTRY.match(line) if fence is None else None
        if not entry:
            lines.append(line)
            continue
        markers = list(MARKER.finditer(line))
        try:
            if markers:
                if len(markers) != 1:
                    raise ValueError('multiple tracking comments')
                meta = json.loads(markers[0][1])
                if not isinstance(meta, dict) or meta.get('v') != 1:
                    raise ValueError('unknown tracking format')
                for key in ('id', 'doi', 'arxiv_id', 's2_id', 'url', 'citation_source'):
                    if key in meta and not isinstance(meta[key], str):
                        raise ValueError('invalid identity/source field')
            elif '<!-- autoliter:' in line:
                raise ValueError('malformed tracking comment')
            else:
                meta = _legacy_identity(line)
            if not meta.get('id'):
                logger.info("Citation refresh skipped: no stable identifier for %s", entry[1])
                lines.append(line)
                continue
            counts = [match for match in COUNT.finditer(line, entry.end())
                      if not any(marker.start() <= match.start() < marker.end() for marker in markers)]
            if len(counts) > 1:
                raise ValueError('multiple citation fields')
            # The title and any user's trailing text are never used as replacements.
            key = tuple(meta.get(k) for k in ('citation_source', 'doi', 'arxiv_id', 's2_id', 'url'))
            if key not in cache:
                cache[key] = _lookup(meta, entry[1], proxy, semantic_scholar)
            result = cache[key]
            if result is None:
                lines.append(line)
                continue
            count, source, s2_id = result
            text = '(Citations {})'.format(count)
            if counts:
                match = counts[0]
                updated = line[:match.start()] + text + line[match.end():]
            else:
                position = markers[0].start() if markers else len(line.rstrip('\r\n'))
                prefix = '' if line[:position].endswith(' ') else ' '
                suffix = ' ' if markers else ''
                updated = line[:position] + prefix + text + suffix + line[position:]
            meta.update(citation_count=count, citation_source=source, citation_checked_at=_checked_at())
            if s2_id:
                meta['s2_id'] = s2_id
            comment = metadata_comment(meta)
            if markers:
                updated = MARKER.sub(lambda _: comment, updated, count=1)
            else:
                position = len(updated.rstrip('\r\n'))
                updated = updated[:position] + ' ' + comment + updated[position:]
            lines.append(updated)
        except (ValueError, TypeError, KeyError) as exc:
            logger.warning("Citation refresh skipped for %s: %s", entry[1], exc)
            lines.append(line)
    return ''.join(lines)


def refresh_note_citations(note_file, proxy=None, semantic_scholar=False):
    with open(note_file, encoding='utf-8', newline='') as stream:
        content = stream.read()
    updated = refresh_citations(content, proxy=proxy, semantic_scholar=semantic_scholar)
    if updated != content:
        with open(note_file, encoding='utf-8', newline='') as stream:
            if stream.read() != content:
                logger.warning("Note changed during lookup; refresh skipped for %s", os.path.basename(note_file))
                return
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                             dir=os.path.dirname(os.path.abspath(note_file)),
                                             prefix='.autoliter-', suffix='.tmp', delete=False) as stream:
                temporary_path = stream.name
                stream.write(updated)
            os.replace(temporary_path, note_file)
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)
        logger.info("Citation fields refreshed in %s", os.path.basename(note_file))
    else:
        logger.info("No citation fields changed in %s", os.path.basename(note_file))
