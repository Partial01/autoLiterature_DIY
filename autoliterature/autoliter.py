import logging 
import argparse
import os 

from .utils import patternRecognizer, note_modified, get_pdf_paths, get_pdf_paths_from_notes, get_update_content, get_pdf_paths_from_notes_dict
from .citations import refresh_note_citations

logging.basicConfig()
logger = logging.getLogger('AutoLiter')
logger.setLevel(logging.INFO)


def set_args():
    parser = argparse.ArgumentParser(description='autoLiterature')
    parser.add_argument('-i', '--input', required=True, type=str, default=None,
                        help="The path to the note file or note file folder.")
    parser.add_argument('-o', '--output', type=str, default=None,
                        help='Folder path to save paper pdfs and iamges. NOTE: MUST BE FOLDER')
    parser.add_argument('-p', '--proxy', type=str, default=None, 
                        help='The proxy. e.g. 127.0.0.1:1080')
    parser.add_argument('-d', '--delete', action='store_true',
                        help='Delete unreferenced attachments in notes. Use with caution, '
                        'when used, -i must be a folder path including all notes')
    parser.add_argument('-m', '--migration', type=str, default=None, 
                        help="the pdf folder path you want to reconnect to")
    parser.add_argument('--semantic-scholar', action='store_true',
                        help='Enable optional Semantic Scholar enrichment.')
    parser.add_argument('--refresh-citations', action='store_true',
                        help='Refresh existing citation counts only; no PDFs or -o required. '
                             'Add --semantic-scholar to refresh S2 counts.')
    args = parser.parse_args()
    if args.refresh_citations and (args.output or args.delete or args.migration):
        parser.error('--refresh-citations cannot be combined with -o, -d, or -m')
    
    return args 

def check_args():
    args = set_args()
    input_path = args.input
    output_path = args.output 
    delete_bool = args.delete
    migration_path = args.migration
    proxy = args.proxy
    semantic_scholar = args.semantic_scholar
        
    return input_path, output_path, delete_bool, proxy, migration_path, args.refresh_citations, semantic_scholar


def get_bib_and_pdf(note_file, output_path, proxy, paper_recognizer, semantic_scholar=False):
    
    pdfs_path = output_path
    if not os.path.exists(pdfs_path):
        os.makedirs(pdfs_path)
    
    with open(note_file, 'r', encoding='utf-8') as f:
        content = f.read()
            
    m = paper_recognizer.findall(content)
    logger.info("Papers to process: %s", len(m))

    if not m:
        logger.info("No paper placeholders found; %s unchanged.", os.path.basename(note_file))
    else:
        # TODO add pd_online link in note file
        replace_dict = get_update_content(
            m,
            note_file,
            pdfs_path,
            proxy=proxy,
            semantic_scholar=semantic_scholar,
        )
            
        return replace_dict


def file_update(input_path, output_path, proxy, paper_recognizer, semantic_scholar=False):
    
    replace_dict =  get_bib_and_pdf(input_path, output_path,
                                    proxy, paper_recognizer, semantic_scholar=semantic_scholar)
    
    if replace_dict:
        note_modified(paper_recognizer, input_path, **replace_dict)


def main():
    input_path, output_path, delete_bool, proxy, migration_path, refresh_counts, semantic_scholar = check_args()

    if refresh_counts:
        if os.path.isfile(input_path):
            refresh_note_citations(input_path, proxy=proxy, semantic_scholar=semantic_scholar)
        elif os.path.isdir(input_path):
            for root, _, files in os.walk(input_path):
                for file in files:
                    if file.lower().endswith(('.md', '.markdown')):
                        refresh_note_citations(os.path.join(root, file), proxy=proxy,
                                               semantic_scholar=semantic_scholar)
        else:
            logger.error("Input path does not exist: %s", os.path.basename(input_path))
            raise SystemExit(2)
        return
    
    if output_path:
        paper_recognizer = patternRecognizer(r'- \{\{?[^{}\r\n]+\}\}?')
        
        if os.path.isfile(input_path):
            logger.info("Updating %s", os.path.basename(input_path))
            file_update(input_path, output_path, proxy, paper_recognizer, semantic_scholar=semantic_scholar)
            
        elif os.path.isdir(input_path):
            note_paths = []
            for root, _, files in os.walk(input_path):
                for file in files:
                    if file.lower().endswith('md') or file.lower().endswith('markdown'):
                        note_paths.append(os.path.join(root, file))
            for note_path in note_paths:
                logger.info("Updating %s", os.path.basename(note_path))
                file_update(note_path, output_path, proxy, paper_recognizer, semantic_scholar=semantic_scholar)
        else:
            logger.info("Input path does not exist: %s", os.path.basename(input_path))
    
    
        # Delete unreferenced attachments
        if delete_bool:
            if os.path.isfile(input_path):
                logger.info("To delete unreferenced PDFs, -i must be the folder containing all notes. Use with caution.")
            else:
                pdf_path_recognizer = patternRecognizer(r'\[pdf\]\(.{5,}\.pdf\)')
                pdf_paths_in_notes = get_pdf_paths_from_notes(input_path, pdf_path_recognizer)
                pdf_paths = get_pdf_paths(output_path)
                # TODO: Normalize path separators across platforms.
                pdf_paths_in_notes = [os.path.abspath(i).replace('\\', '/') for i in pdf_paths_in_notes]
                pdf_paths = [os.path.abspath(i).replace('\\', '/') for i in pdf_paths]
                
                removed_pdf_paths = list(set(pdf_paths) - set(pdf_paths_in_notes))
                try:
                    for pdf_p in removed_pdf_paths:
                        os.remove(pdf_p)
                except:
                    pass 
                
                logger.info("Deleted %s PDF files", len(removed_pdf_paths))
            
    
    if migration_path:
        pdf_path_recognizer = patternRecognizer(r'\[pdf\]\(.{5,}\.pdf\)')
        
        pdf_paths = get_pdf_paths(migration_path)
        pdf_paths_in_notes = get_pdf_paths_from_notes_dict(input_path, pdf_path_recognizer)
        
        # match based on paper title
        matched_numb = 0
        pdf_paths_dict = {os.path.basename(i): i for i in pdf_paths}
        for md_file, pdf_paths_ in  pdf_paths_in_notes.items():
                
            pdf_paths_in_notes_dict = {os.path.basename(i): i for i in pdf_paths_}
            matched_pdfs = pdf_paths_dict.keys() & pdf_paths_in_notes_dict.keys()
            
            matched_numb += len(matched_pdfs)

            # os.path.relpath(pdf_path, note_file).split('/',1)[-1]
            replace_paths_dict = {}
            for matched in matched_pdfs:
                replaced_str = os.path.relpath(pdf_paths_dict[matched], md_file).split('/',1)[-1]
                replaced_str = "[pdf]({})".format(replaced_str)
                ori_str = "[pdf]({})".format(pdf_paths_in_notes_dict[matched])
                replace_paths_dict[ori_str] = replaced_str
            
            if replace_paths_dict: 
                note_modified(pdf_path_recognizer, md_file, **replace_paths_dict)
        
        logger.info("Matched %s PDF files", matched_numb)
        

    if not output_path and not migration_path:
        logger.info("Missing -o or -m; no changes made. Use -h for help.")


if __name__ == "__main__":
    main()
