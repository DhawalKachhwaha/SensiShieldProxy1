from fastapi import FastAPI, UploadFile, File
from presidio_analyzer import AnalyzerEngine
from extractTextFromPDF import extract_text_hybrid
import tempfile
import os

app = FastAPI()

analyzer = AnalyzerEngine()

# -----------------------
# TEXT SCAN
# -----------------------
def detect_pii(text):
    return analyzer.analyze(
        text=text,
        language="en",
        score_threshold=0.6
    )

def make_decision(results):
    decision = "allow"

    for r in results:
        print(r.entity_type, r.score)

        if r.score > 0.85:
            decision = "block"
            break

    return decision

# -----------------------
# NORMAL TEXT ENDPOINT
# -----------------------
@app.post("/scan")
async def scan(data: dict):

    text = data.get("text", "")

    results = detect_pii(text)

    decision = make_decision(results)

    return {
        "decision": decision,
        "entities": [r.entity_type for r in results]
    }

# -----------------------
# FILE SCAN ENDPOINT
# -----------------------
@app.post("/scan-file")
async def scan_file(file: UploadFile = File(...)):

    # Save uploaded file temporarily
    suffix = os.path.splitext(file.filename)[1]

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        contents = await file.read()
        tmp.write(contents)
        temp_path = tmp.name

    try:
        # OCR + extraction
        pages = extract_text_hybrid(temp_path, dpi=120, use_parallel=False)

        text = "\n".join(pages)

        print("EXTRACTED FILE TEXT:")
        print(text[:1000])

        results = detect_pii(text)

        decision = make_decision(results)

        return {
            "decision": decision,
            "entities": [r.entity_type for r in results]
        }
        print("\n=== FILE TEXT ===")
        print(text[:1000])
        print("\n=== RESULTS ===")
        for r in results:
            print(r.entity_type, r.score)
        print("FINAL DECISION:", decision)
    except Exception as ex:
        print('Exception occured:', ex)
        return {
            "decision": "error",
            "error": str(ex)
        }
    finally:
        os.remove(temp_path)
    