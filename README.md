# autoLiterature

**Language:** [English](README.md) | [中文](README.zh-CN.md)

**autoLiterature** is a Python command-line tool for automatic literature note management. Inspired by [Mu Li](https://www.bilibili.com/video/BV1nA41157y4).

**Recognition rules:**

- Automatically recognizes `- {xxx}`.
- When a note contains `- {paper_id}`, autoLiterature downloads the paper metadata, but **does not download the PDF**.
- When a note contains `- {{paper_id}}`, autoLiterature downloads the paper metadata and the PDF.

Note: `paper_id` supports `doi` for published papers, and `arxiv_id`, `biorxiv_id`, or `medrxiv_id` for preprints.

## Installation

1. Install from pip

```bash
pip install autoliter
# or
pip3 install autoliter
```

2. Install from source

```bash
git clone https://github.com/WilmerWang/autoLiterature.git
cd autoLiterature
python setup.py install

# After local code changes, run this in the project directory:
pip install -e .
```

### Command options

```bash
autoliter

options:
  -h, --help            show this help message and exit
  -i INPUT, --input INPUT
                        The path to the note file or note file folder.
  -o OUTPUT, --output OUTPUT
                        Folder path to save paper pdfs and iamges. NOTE: MUST BE FOLDER
  -p PROXY, --proxy PROXY
                        The proxy. e.g. 127.0.0.1:1080
  -d, --delete          Delete unreferenced attachments in notes. Use with caution,
                        when used, -i must be a folder path including all notes
  -m MIGRATION, --migration MIGRATION
                        the pdf folder path you want to reconnect to
  --semantic-scholar    Enable optional Semantic Scholar enrichment.
```

## Usage

### Basic usage

Assume `input` is the path to a literature note file or folder, and `output` is the folder where PDFs should be saved.

```bash
# Update all Markdown files under the input folder
autoliter -i input -o output

# Update only input/example.md
autoliter -i input/example.md -o output

# Optional: when -i is a folder, -d deletes PDFs in the output folder that are not referenced by the notes
autoliter -i input -o output -d

# Optional: enable Semantic Scholar enrichment for S2 links, citation counts, venue, and related metadata
autoliter -i input -o output --semantic-scholar
```

`--semantic-scholar` is disabled by default. It can run without an API key, but may hit the official Semantic Scholar rate limit. For more stable requests, set `SEMANTIC_SCHOLAR_API_KEY` first.

```powershell
$env:SEMANTIC_SCHOLAR_API_KEY = "your_api_key"
```

### Migrate notes and PDF files

When moving literature notes or the PDF folder, PDF links in the notes may become invalid. Use `-m` to reconnect PDF files and literature notes. The PDF filenames in the target PDF folder must remain the same as before.

```bash
# Update all Markdown files under the input folder
autoliter -i input -m movedPDFs/

# Update only input/example.md
autoliter -i input/example.md -m movedPDFs/
```

For more examples, see the local [Jupyter notebook](doc/autolter_example.ipynb), or view the `doc` folder on [GitHub](https://github.com/WilmerWang/autoLiterature.git).

## License

MIT
