from fastapi import FastAPI, UploadFile, File
import hashlib
from redisCache import cache_result, get_cached_result
from presidio_analyzer import AnalyzerEngine
from extractTextFromPDF import extract_text_hybrid
from dlpProxy import log
import fitz
import tempfile
import os
import time

app = FastAPI()

analyzer = AnalyzerEngine()
LARGE_FILE_LIMIT = 100 * 1024 * 1024

# =========================================================
# CORE SCANNING LOGIC
# =========================================================

def detect_pii(text):

    return analyzer.analyze(
        text=text,
        language="en",
         entities=[
        "CREDIT_CARD",
        "IBAN_CODE",
        "CRYPTO",
    ],
        score_threshold=0.6
    )


def make_decision(results):

    for r in results:

        print(r.entity_type, r.score)

        if r.score > 0.7:
            return "block"

    return "allow"


def scan_text_content(text):

    results = detect_pii(text)

    decision = make_decision(results)

    return {
        "decision": decision,
        "entities": [r.entity_type for r in results]
    }


# =========================================================
# TEXT ENDPOINT
# =========================================================

@app.post("/scan")
async def scan(data: dict):

    text = data.get("text", "")

    return scan_text_content(text)


# =========================================================
# COMMON FILE SCAN LOGIC
# =========================================================

async def process_uploaded_file(file: UploadFile):
    suffix = os.path.splitext(file.filename or "upload.pdf")[1]
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        contents = await file.read()
        is_large_file = len(contents) > LARGE_FILE_LIMIT
        log(f"LARGE FILE: {is_large_file}")
        file_hash = hashlib.sha256(contents).hexdigest()
        log(f"FILE HASH: {file_hash}")
        cached = get_cached_result(file_hash)
        if cached:
            log("CACHE HIT")
            return cached
        log("CACHE MISS")
        tmp.write(contents)
        tmp.flush()  # <-- force write to disk
        os.fsync(tmp.fileno())  # <-- extra guarantee, OS-level flush
        temp_path = tmp.name

    # Now open OUTSIDE the with block, after the file is closed
    log(f"====== Server Process Upload ======")
    log(f"FILE SIZE: {len(contents)}")
    log(f"PDF HEADER: {contents[:20]}")
    log(f"TEMP PATH: {temp_path}")
    log(f"FILE EXISTS: {os.path.exists(temp_path)}")
    log(f"DISK SIZE: {os.path.getsize(temp_path)}")

    try:
        doc = fitz.open(temp_path)
        log(f"PDF PAGE COUNT: {len(doc)}")
        doc.close()

        # rest of your scanning logic...
        if is_large_file:

            log("USING LARGE FILE MODE")

            pages = extract_text_hybrid(
                temp_path,
                dpi=100,
                max_pages=20,
                use_parallel=False
            )

        else:

            pages = extract_text_hybrid(
                temp_path,
                dpi=120,
                use_parallel=False
            )
        text = "\n".join(pages)
        result = scan_text_content(text)
        cache_result(file_hash, result)
        log("RESULT CACHED")
        return result

    except Exception as ex:
        log(f"Exception: {ex}")
        return {"decision": "error", "error": str(ex)}

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)




# =========================================================
# OPENAI FILE ENDPOINT
# =========================================================

@app.post("/scan-file/openai")
async def scan_openai_file(
    file: UploadFile = File(...)
):

    return await process_uploaded_file(file)


# =========================================================
# CLAUDE FILE ENDPOINT
# =========================================================

@app.post("/scan-file/claude")
async def scan_claude_file(
    file: UploadFile = File(...)
):

    return await process_uploaded_file(file)