# Citation sources and refresh behavior

## Paper identifiers

New literature entries keep their original paper identifier and available DOI, arXiv ID, Semantic Scholar ID, and source URL in a hidden `<!-- autoliter: ... -->` comment. When a citation count is available, the comment also records its provider and the UTC query time.

An ACM catalog identifier is not always a registered DOI. Crossref describes `10.5555` as a [test and unmaintained-record prefix](https://community.crossref.org/t/crossref-test-account-prefixes/13263). A Crossref or doi.org 404 means that provider cannot resolve the identifier; a publisher's 403 means access was refused.

For USENIX papers, an official presentation URL can supply metadata directly through the page's `citation_*` tags. This does not depend on Crossref registration. See [USENIX source examples](usenix-examples.md).

## Refresh citation counts

Run from an installed checkout:

```bash
autoliter -i notes/example.md --refresh-citations --semantic-scholar
```

Omit `--semantic-scholar` to query Crossref entries only. Refresh needs no output directory and cannot be combined with `-o`, `-d`, or `-m`.

Refresh updates only `(Citations N)` and the tracking comment. It preserves titles, authors, links, handwritten notes, images, and line endings. It does not download PDFs or delete attachments. Fenced Markdown code blocks are skipped. If the note changes during the network lookup, the file is skipped before writing.

The recorded provider determines which source is queried. A Crossref count never replaces a count attributed to Semantic Scholar. Timeouts, rate limits, missing counts, and missing identifiers preserve the old line and query time. Zero is a valid count.

## Existing entries without tracking comments

The refresh command recovers identifiers from links in the entry:

| Available link | Inferred count provider |
| --- | --- |
| Semantic Scholar paper | Semantic Scholar |
| DOI or ACM DOI/PDF | Crossref |
| arXiv | Semantic Scholar |

The table's order sets the priority. Entries without a recoverable identifier, or with conflicting identifiers of the same kind, are skipped. The original count provider cannot be proven from links alone. Correct the tracking information first if you know the inferred provider is wrong.

For an official USENIX URL without a saved S2 ID, an S2 query can use the entry's title. Only a single exact match is accepted after normalizing case, whitespace, and BibTeX protection braces. The resulting S2 ID is saved for later refreshes. Ambiguous and approximate title matches are skipped.

## Diagnose an unresolved DOI

The read-only probe inspects DOI placeholders in a Markdown file and prints HTTP results from Crossref, doi.org, ACM, and Semantic Scholar:

```bash
python scripts/diagnose_dois.py notes/example.md
```

The probe does not modify notes or download PDFs. Results depend on provider availability and access restrictions.

## Run regression checks

```bash
python -m unittest discover -s tests -p test_doi_refresh.py -v
```

The regression checks use mocked provider responses and temporary notes. They cover source attribution, failure preservation, identifier recovery, and the CLI refresh path.
