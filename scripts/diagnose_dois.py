"""Read-only HTTP probes for DOI failures. Does not change notes or download PDFs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import re

import requests


def probe(target):
    provider, doi, url, headers = target
    try:
        response = requests.get(url, headers=headers, timeout=20)
        result = {"provider": provider, "doi": doi, "status": response.status_code,
                  "url": response.url, "content_type": response.headers.get("Content-Type")}
        try:
            data = response.json()
            if provider == "crossref":
                data = data.get("message", data)
            result["data"] = data
        except ValueError:
            result["body_preview"] = response.text[:300]
        return result
    except requests.RequestException as exc:
        return {"provider": provider, "doi": doi, "error": str(exc)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("note", help="Markdown file containing DOI placeholders")
    args = parser.parse_args()
    with open(args.note, encoding="utf-8") as stream:
        dois = sorted(set(re.findall(r"\{(10\.\d{4,9}/[^{}\s]+)\}", stream.read())))
    targets = []
    for doi in dois:
        targets.extend([
            ("crossref-http", doi, "http://api.crossref.org/works/" + doi, {}),
            ("crossref", doi, "https://api.crossref.org/works/" + doi, {}),
            ("doi-csl", doi, "https://doi.org/" + doi,
             {"Accept": "application/vnd.citationstyles.csl+json"}),
            ("acm", doi, "https://dl.acm.org/doi/" + doi, {}),
            ("semantic-scholar", doi,
             "https://api.semanticscholar.org/graph/v1/paper/DOI:" + doi
             + "?fields=title,year,venue,url,citationCount,openAccessPdf,authors,externalIds", {}),
        ])
    # Keep Semantic Scholar calls serial, at the documented one-request/second rate.
    other_targets = [target for target in targets if target[0] != "semantic-scholar"]
    with ThreadPoolExecutor(max_workers=3) as executor:
        for result in executor.map(probe, other_targets):
            print(json.dumps(result, ensure_ascii=True), flush=True)
    import time
    for target in targets:
        if target[0] == "semantic-scholar":
            print(json.dumps(probe(target), ensure_ascii=True), flush=True)
            time.sleep(1)


if __name__ == "__main__":
    main()
