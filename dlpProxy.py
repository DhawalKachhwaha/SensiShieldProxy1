#dlpProxy.py
from mitmproxy import http
import requests
import json

SCAN_API = "http://localhost:8000/scan" #Change to server IP - currently runs in localhost


# LLM PROMPT REQUEST TEXT EXTRACTION
def extract_prompt(content):
    if not content:
        return ""

    content = content.strip()

    if not (content.startswith("{") or content.startswith("[")):
        return ""

    try:
        data = json.loads(content)
    except Exception:
        return ""

    # Handle list payloads
    if isinstance(data, list):
        return ""

    messages = data.get("messages", [])
    text_chunks = []

    for m in messages:

        if not isinstance(m, dict):
            continue

        role = m.get("role") or m.get("author", {}).get("role")

        if role != "user":
            continue

        content_obj = m.get("content")

        if isinstance(content_obj, dict):
            parts = content_obj.get("parts", [])

            text_chunks.extend(
                [p for p in parts if isinstance(p, str)]
            )

        elif isinstance(content_obj, str):
            text_chunks.append(content_obj)

    return " ".join(text_chunks).strip()


# SCAN TEXT - CHECK server.py 
def scan_text(text):
    try:
        response = requests.post(
            SCAN_API,
            json={"text": text},
            timeout=5
        )
        return response.json().get("decision")
    except Exception as e:
        print("Scan error:", e)
        return "allow"


# HANDLE RAW FILE UPLOAD 
def handle_raw_file_upload(flow):
    content = flow.request.raw_content
    content_type = flow.request.headers.get("content-type", "")

    if not content:
        return

    print("RAW FILE UPLOAD:", len(content), "bytes", content_type)

    try:
        files = {
            "file": ("upload.pdf", content)
        }

        response = requests.post(
            "http://localhost:8000/scan-file",
            files=files,
            timeout=30
        )

        print("STATUS:", response.status_code)
        print("RAW RESPONSE:", response.text)
        data = response.json()
        print("PARSED RESPONSE:", data)
        decision = data.get("decision")

        print("FILE Decision:", decision)

        if decision == "block":
            flow.response = http.Response.make(
                403,
                b"Blocked: Sensitive data in file",
                {"Content-Type": "text/plain"}
            )

    except Exception as e:
        print("File scan error:", e)
# HANDLE MULTIPART (fallback)
def handle_multipart_upload(flow):
    multipart = flow.request.multipart_form

    if not multipart:
        return

    for name, value in multipart.items():
        if hasattr(value, "filename"):
            filename = value.filename
            content = value.content

            print("MULTIPART FILE:", filename, len(content))

            try:
                text = content.decode("utf-8", errors="ignore")
            except:
                text = ""

            if not text:
                continue

            decision = scan_text(text)

            if decision == "block":
                flow.response = http.Response.make(
                    403,
                    b"Blocked: Sensitive data in file",
                    {"Content-Type": "text/plain"}
                )
                return


# MAIN ENTRY
def request(flow: http.HTTPFlow):
    try:
        host = flow.request.pretty_host
        path = flow.request.path
        method = flow.request.method
        content_type = flow.request.headers.get("content-type", "")

        # -----------------------
        # 1. FILE UPLOAD (RAW PUT to blob storage) - 
        # CHATGPT uses oaiusercontent.com for PUT
        # 
        # -----------------------
        if (
            method in ["PUT", "POST"] and
            (
                "oaiusercontent.com" in host or
                "anthropic.com" in host or
                "claudeusercontent.com" in host
            )
        ):
            handle_raw_file_upload(flow)
            return

        # 2. MULTIPART FILE (fallback)
        if "multipart/form-data" in content_type:
            handle_multipart_upload(flow)
            return

        # 3. TEXT REQUESTS in LLM
        if "/backend-api/conversation" in path or "/backend-api/f/conversation" in path or "/v1/" in path:
            flow.request.decode()
            raw = flow.request.text or ""

            content = extract_prompt(raw)

            if not content:
                return

            decision = scan_text(content)

            if decision == "block":
                flow.response = http.Response.make(
                    403,
                    b"Blocked: Sensitive data detected",
                    {"Content-Type": "text/plain"}
                )

            print("Text:\n", content[:200])
            print("Decision\n:", decision)

    except Exception as e:
        print("Error:", e)