#extractTextFromPDF.py
import pytesseract
from pdf2image import convert_from_path
import fitz  # PyMuPDF
from presidio_analyzer import AnalyzerEngine
import re
import os
import requests
from multiprocessing import Pool, cpu_count

#Legal Agreement General Terms

LEXICON = {"structure":["article i", "article ii", "section 1.1", "section 2.3", "clause", "hereinafter", "whereas", "hereto", "hereby", "thereof", "therein"],
           "obligation": ["shall", "shall not", "agrees to", "is obligated to", "undertakes to", "covenant", "warrants", "represents"],
           "boilerplate":["termination", "force majeure", "entire agreement", "amendment", "severability", "waiver", "assignment"],
           "legal":["indemnify", "liability", "damages", "governing law", "jurisdiction", "applicable law", "compliance with laws"],
           "strong":["non-disclosure agreement", "nda", "confidential information", "proprietary information", "disclosing party", "receiving party", "mutual agreement", "unilateral agreement", "terms and conditions of this agreement"]}



analyzer = AnalyzerEngine()

#Check - https://karthikeyanrathinam.medium.com/extracting-text-and-images-from-pdfs-using-python-a-step-by-step-guide-b9c8506fd613 for explanation
# ---------------------------
# Download Tesseract language data
# ---------------------------
def download_tesseract_lang_data(lang):
    tessdata_dir = os.path.join(os.getenv('TESSDATA_PREFIX', ''), 'tessdata')
    if not os.path.exists(tessdata_dir):
        os.makedirs(tessdata_dir)

    lang_file = os.path.join(tessdata_dir, f'{lang}.traineddata')
    if not os.path.exists(lang_file):
        url = f'https://github.com/tesseract-ocr/tessdata_best/raw/main/{lang}.traineddata'
        r = requests.get(url)
        with open(lang_file, 'wb') as f:
            f.write(r.content)

# OCR function (for multiprocessing)
def ocr_image(args):
    page_num, image, lang = args
    config = r'--oem 3 --psm 6'
    text = pytesseract.image_to_string(image, lang=lang, config=config)
    return page_num, text.strip()

# Main extraction pipeline
def extract_text_hybrid(input_path, dpi=200, lang='eng', use_parallel=True, max_pages=12):
    # Ensure languages exist
    for l in lang.split('+'):
        download_tesseract_lang_data(l)

    # Check if it's an image
    ext = os.path.splitext(input_path)[1].lower()
    if ext in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
        from PIL import Image
        img = Image.open(input_path)
        _, text = ocr_image((0, img, lang))
        return [text]

    # Assume PDF
    try:
        input_pdf = fitz.open(input_path)
    except Exception as e:
        print(f"Error opening file {input_path}: {e}")
        return []

    total_pages = len(input_pdf)
    results = [""] * total_pages
    pages_to_ocr = []
    MAX_OCR_PAGES=max_pages

    # Try native extraction
    for page_num in range(total_pages):
        page = input_pdf[page_num]
        text = page.get_text("text").strip()

        if text:
            results[page_num] = text
        else:
            pages_to_ocr.append(page_num)

    # OCR required pages for scanned PDFs

    if pages_to_ocr:

        print(f"OCR needed for {len(pages_to_ocr)} / {total_pages} pages")

        # Limit OCR workload
        if len(pages_to_ocr) > MAX_OCR_PAGES:

            important_pages = set()

            # First pages
            important_pages.update(
                pages_to_ocr[:3]
            )

            # Last pages
            important_pages.update(
                pages_to_ocr[-3:]
            )

            # Middle pages
            middle = pages_to_ocr[3:-3]

            important_pages.update(
                middle[:MAX_OCR_PAGES - 6]
            )

            pages_to_ocr = sorted(
                list(important_pages)
            )

        try:

            ocr_results = []

            # Render ONLY required pages
            for p in pages_to_ocr:

                images = convert_from_path(
                    input_path,
                    dpi=dpi,
                    first_page=p + 1,
                    last_page=p + 1
                )

                if not images:
                    continue

                image = images[0]

                if use_parallel:
                    ocr_results.append(
                        ocr_image((p, image, lang))
                    )
                else:
                    ocr_results.append(
                        ocr_image((p, image, lang))
                    )

            for page_num, text in ocr_results:

                results[page_num] = text

        except Exception as e:

            print(f"OCR error: {e}")

    input_pdf.close()
    return results


def detect_pii(text):
    results = analyzer.analyze(
        text=text,
        language="en",
         entities=[
        "CREDIT_CARD",
        "IBAN_CODE",
        "CRYPTO",
    ],
        score_threshold=0.6
    )
    return results

def scan_text(text):
    legal_score = score_legal_text(text)
    pii_results = detect_pii(text)
    decision = "allow"
    for r in pii_results:
        if r.score > 0.85:
            decision = "block"
            break
    return {
        "decision": decision,
        "pii": [r.entity_type for r in pii_results],
        "legal_score": legal_score
    }
    
def score_pages(pages):
    page_scores = []
    for text in pages:
        score = score_legal_text(text)
        page_scores.append(score)
    return page_scores
def aggregate_document_score(page_scores):
    if not page_scores:
        return 0

    avg_score = sum(page_scores) / len(page_scores)
    max_score = max(page_scores)

    # Weighted combination
    final_score = (0.6 * max_score) + (0.4 * avg_score)

    return final_score
def classify_document(page_scores, threshold=1.2):
    doc_score = aggregate_document_score(page_scores)

    is_legal = doc_score > threshold

    return {
        "is_legal": is_legal,
        "doc_score": doc_score,
        "page_scores": page_scores
    }
def score_legal_text(text):
    text_lower = text.lower()
    score = 0

    def count_matches(terms, weight):
        nonlocal score
        for term in terms:
            if term in text_lower:
                score += weight

    count_matches(LEXICON["strong"], 0.6)
    count_matches(LEXICON["structure"], 0.3)
    count_matches(LEXICON["obligation"], 0.2)
    count_matches(LEXICON["legal"], 0.2)
    count_matches(LEXICON["boilerplate"], 0.25)

    # Extra structural boosts
    if re.search(r"\b\d+\.\d+\b", text):
        score += 0.3  # clause numbering

    if text_lower.count("shall") > 3:
        score += 0.3

    return score
# ---------------------------
# Example usage
# ---------------------------
if __name__ == "__main__":
    input_pdf_path = "/home/ritwix/Downloads/Downloads/Dart Legacy-Agreement.pdf"
    languages = "eng+spa+fra"

    pages = extract_text_hybrid(input_pdf_path, lang=languages)
    page_scores = score_pages(pages)
    result = classify_document(page_scores)
    print("\n=== DOCUMENT RESULT ===")
    print("Legal Document:", result["is_legal"])
    print("Document Score:", result["doc_score"])
    print("Page Scores:", result["page_scores"])

