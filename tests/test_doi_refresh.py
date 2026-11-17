import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from autoliterature.autoliter import main
from autoliterature.citations import (
    MARKER, metadata_comment, refresh_citations, refresh_note_citations, tracking_metadata,
)
from autoliterature.crossref import crossrefInfo
from autoliterature.downloads import classify, get_paper_info_from_paperid
from autoliterature.semantic_scholar import _select_title_match
from autoliterature.utils import format_literature_entry, patternRecognizer


S2_ID = 'a' * 40
USENIX_URL = 'https://www.usenix.org/conference/usenixsecurity25/presentation/yu-zheng'
DOI = '10.1145/1234.5678'
BIB = {'title': 'A paper', 'author': 'An Author', 'doi': DOI, 'cited_count': 5}


def metadata(line):
    return json.loads(MARKER.search(line)[1])


class DoiResolutionTests(unittest.TestCase):
    def test_crossref_404_reports_status_and_unmaintained_prefix(self):
        client = crossrefInfo()
        response = Mock(status_code=404)
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
        with patch.object(client.sess, 'get', return_value=response) as get:
            with self.assertLogs('crossref', level='WARNING') as logs:
                self.assertIsNone(client.get_info_by_doi('10.5555/3766078.3766304'))
        self.assertIn('HTTP 404', ' '.join(logs.output))
        self.assertIn('USENIX', ' '.join(logs.output))
        self.assertTrue(get.call_args.args[0].startswith('https://'))
        self.assertEqual(get.call_args.kwargs['timeout'], 15)

    def test_crossref_distinguishes_timeout_network_and_invalid_json(self):
        for error, message in [(requests.Timeout(), 'timeout'),
                               (requests.ConnectionError('offline'), 'network error'),
                               (ValueError('bad JSON'), 'invalid JSON')]:
            client = crossrefInfo()
            with patch.object(client.sess, 'get', side_effect=error):
                with self.assertLogs('crossref', level='WARNING') as logs:
                    self.assertIsNone(client.get_info_by_doi(DOI))
            self.assertIn(message, ' '.join(logs.output))

    def test_crossref_handles_missing_optional_fields_and_selects_pdf(self):
        bib = crossrefInfo().extract_json_info({
            'title': ['A paper'], 'DOI': DOI, 'issued': {'date-parts': [[2025]]},
            'link': [{'URL': 'https://example.org/article.xml', 'content-type': 'text/xml'},
                     {'URL': 'https://example.org/paper.pdf', 'content-type': 'application/pdf'}],
        })
        self.assertEqual(bib['year'], '2025')
        self.assertEqual(bib['pdf_link'], 'https://example.org/paper.pdf')
        self.assertEqual(bib['url'], 'https://doi.org/' + DOI)
        self.assertIsNone(bib['cited_count'])

    def test_usenix_input_reads_official_citation_metadata_without_doi(self):
        response = Mock()
        response.text = '''<meta name="citation_title" content="{SoK}: A paper">
            <meta name="citation_author" content="First Author">
            <meta name="citation_author" content="Second Author">
            <meta name="citation_publication_date" content="2025">
            <meta name="citation_conference_title" content="USENIX Security 25">
            <meta name="citation_pdf_url" content="https://www.usenix.org/system/files/paper.pdf">'''
        with patch('autoliterature.usenix.requests.get', return_value=response):
            bib = get_paper_info_from_paperid(USENIX_URL, enrich_semantic=False)
        self.assertEqual(bib['title'], 'SoK: A paper')
        self.assertEqual(bib['author'], 'First Author and Second Author')
        self.assertEqual(bib['url'], USENIX_URL)
        self.assertIsNone(bib['doi'])
        self.assertIsNone(bib['cited_count'])

    def test_doi_classification_supports_long_registrant_prefixes(self):
        self.assertEqual(classify('10.123456789/example'), 'doi')
        self.assertEqual(classify('10.1101/2024.01.01.12345'), 'medbiorxivId')

    def test_failed_placeholders_stay_unchanged_on_repeated_replacement(self):
        recognizer = patternRecognizer(r'- \{\{?[^{}\r\n]+\}\}?')
        original = '- {10.5555/missing}\n- {10.1145/found}\n'
        updated = recognizer.multiple_replace(original, **{'- {10.1145/found}': 'found'})
        self.assertEqual(updated, '- {10.5555/missing}\nfound\n')
        self.assertEqual(recognizer.multiple_replace(updated), updated)

    def test_ambiguous_title_matches_are_not_used(self):
        self.assertEqual(_select_title_match({'data': [{'title': 'A paper'}, {'title': 'A paper'}]},
                                            'A paper'), {})
        self.assertEqual(_select_title_match({'data': [{'title': 'SoK: A paper'}]},
                                            '{SoK}: A paper')['title'], 'SoK: A paper')


class CitationRefreshTests(unittest.TestCase):
    def test_generated_entry_retains_identity_source_and_query_time(self):
        line = format_literature_entry(BIB, paper_id=DOI)
        meta = metadata(line)
        self.assertEqual(meta['id'], DOI)
        self.assertEqual(meta['doi'], DOI)
        self.assertEqual(meta['citation_source'], 'crossref')
        self.assertIn('citation_checked_at', meta)
        self.assertIn('(Citations 5)', line)

    def test_only_count_and_comment_change_notes_links_and_crlf_survive(self):
        line = format_literature_entry(BIB, paper_id=DOI).splitlines()[0] + ' 手写备注\r\n'
        original = line + '\t- 自己的总结\r\n\r\n![[pasted image.png]]\r\n'
        with patch('autoliterature.citations.crossrefInfo') as client:
            client.return_value.get_info_by_doi.return_value = {'cited_count': 0}
            updated = refresh_citations(original, semantic_scholar=True)
        self.assertIn('(Citations 0)', updated)
        self.assertEqual(MARKER.sub('', updated), MARKER.sub('', original).replace('(Citations 5)', '(Citations 0)'))
        self.assertEqual(metadata(updated)['citation_count'], 0)
        self.assertEqual(metadata(updated)['citation_source'], 'crossref')

    def test_failure_preserves_entire_original_including_old_date(self):
        original = format_literature_entry(BIB, paper_id=DOI)
        with patch('autoliterature.citations.crossrefInfo') as client:
            client.return_value.get_info_by_doi.return_value = None
            self.assertEqual(refresh_citations(original), original)

    def test_missing_counts_and_negative_values_preserve_original(self):
        original = format_literature_entry(BIB, paper_id=DOI)
        for count in (None, -1, True, '2'):
            with patch('autoliterature.citations.crossrefInfo') as client:
                client.return_value.get_info_by_doi.return_value = {'cited_count': count}
                self.assertEqual(refresh_citations(original), original)

    def test_legacy_s2_link_recovers_identity_and_caches_duplicate_entries(self):
        line = '- **A paper**. *An Author* ([S2](https://www.semanticscholar.org/paper/' + S2_ID + ')) (Citations 5)\n'
        original = line + '\t- 手写笔记\n' + line
        with patch('autoliterature.citations.get_semantic_scholar_info',
                   return_value={'paperId': S2_ID, 'citationCount': 9}) as lookup:
            updated = refresh_citations(original, semantic_scholar=True)
        lookup.assert_called_once_with(paper_id=S2_ID, proxy=None)
        self.assertEqual(updated.count('(Citations 9)'), 2)
        self.assertIn('\t- 手写笔记\n', updated)
        self.assertEqual(metadata(updated)['s2_id'], S2_ID)

    def test_s2_rows_require_opt_in_and_do_not_fall_back_to_crossref(self):
        bib = dict(BIB, semantic_scholar={'paperId': S2_ID, 'citationCount': 20})
        original = format_literature_entry(bib, paper_id=DOI)
        with patch('autoliterature.citations.get_semantic_scholar_info') as lookup:
            with patch('autoliterature.citations.crossrefInfo') as crossref:
                self.assertEqual(refresh_citations(original), original)
                lookup.assert_not_called()
                lookup.return_value = {}
                self.assertEqual(refresh_citations(original, semantic_scholar=True), original)
                crossref.assert_not_called()

    def test_legacy_acm_pdf_and_arxiv_links_can_recover_identifiers(self):
        doi_line = '- **A**. *B* ([PDF](https://dl.acm.org/doi/pdf/' + DOI + ')) (Citations 5)\n'
        arxiv_line = '- **C**. *D* ([PDF](https://arxiv.org/pdf/2501.18820v2.pdf)) (Citations 5)\n'
        with patch('autoliterature.citations.crossrefInfo') as crossref:
            crossref.return_value.get_info_by_doi.return_value = {'cited_count': 7}
            with patch('autoliterature.citations.get_semantic_scholar_info', return_value={'citationCount': 8}) as s2:
                updated = refresh_citations(doi_line + arxiv_line, semantic_scholar=True)
        crossref.return_value.get_info_by_doi.assert_called_once_with(DOI)
        s2.assert_called_once_with(doi=None, arxiv_id='2501.18820', proxy=None)
        self.assertIn('(Citations 7)', updated)
        self.assertIn('(Citations 8)', updated)

    def test_unknown_identity_conflicts_invalid_markers_and_code_are_untouched(self):
        lines = [
            '- **No ID**. *A* (Citations 4)\n',
            '- **Invalid**. *A* <!-- autoliter: bad-json -->\n',
            '- **Invalid**. *A* <!-- autoliter: {"v":99,"id":"x"} -->\n',
            '- **Invalid**. *A* <!-- autoliter: {"v":1,"id":[],"doi":[]} -->\n',
            '- **Conflicting**. *A* ([DOI](https://doi.org/10.1234/a)) ([DOI](https://doi.org/10.1234/b))\n',
            '```markdown\n- **A**. *B* ([DOI](https://doi.org/' + DOI + ')) (Citations 5)\n```\n',
        ]
        with patch('autoliterature.citations.crossrefInfo') as client:
            for original in lines:
                self.assertEqual(refresh_citations(original), original)
            client.assert_not_called()

    def test_usenix_without_initial_count_can_get_s2_count_by_exact_title(self):
        original = format_literature_entry({'title': 'A paper', 'url': USENIX_URL}, paper_id=USENIX_URL)
        with patch('autoliterature.citations.get_semantic_scholar_info',
                   return_value={'citationCount': 3, 'paperId': S2_ID}) as s2:
            updated = refresh_citations(original, semantic_scholar=True)
        s2.assert_called_once_with(doi=None, arxiv_id=None, title='A paper', proxy=None)
        self.assertIn('(Citations 3)', updated)
        self.assertEqual(metadata(updated)['s2_id'], S2_ID)

    def test_untrusted_comment_delimiters_are_escaped(self):
        comment = metadata_comment(tracking_metadata(BIB, 'x --> malicious'))
        self.assertEqual(comment.count('-->'), 1)
        self.assertEqual(metadata(comment)['id'], 'x --> malicious')

    def test_refresh_cli_needs_no_output_and_preserves_file_line_endings(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            path = Path(folder) / 'note.md'
            original = format_literature_entry(BIB, paper_id=DOI).replace('\n', '\r\n')
            path.write_bytes(original.encode('utf-8'))
            with patch.object(sys, 'argv', ['autoliter', '-i', str(path), '--refresh-citations']):
                with patch('autoliterature.citations.crossrefInfo') as client:
                    client.return_value.get_info_by_doi.return_value = {'cited_count': 6}
                    main()
            updated = path.read_bytes().decode('utf-8')
            self.assertIn('(Citations 6)', updated)
            self.assertEqual(updated.count('\r\n'), original.count('\r\n'))
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), ['note.md'])

    def test_file_changed_during_lookup_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as folder:
            path = Path(folder) / 'note.md'
            path.write_text('original', encoding='utf-8')

            def concurrent_edit(*args, **kwargs):
                path.write_text('user edit', encoding='utf-8')
                return 'refreshed'

            with patch('autoliterature.citations.refresh_citations', side_effect=concurrent_edit):
                refresh_note_citations(path)
            self.assertEqual(path.read_text(encoding='utf-8'), 'user edit')

    def test_refresh_cli_rejects_pdf_or_delete_operations(self):
        for extra in (['-o', 'pdfs'], ['-d'], ['-m', 'pdfs']):
            with patch.object(sys, 'argv', ['autoliter', '-i', 'note.md', '--refresh-citations'] + extra):
                with self.assertRaises(SystemExit) as error:
                    main()
            self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
