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

    try:
        data = json.loads(content)
    except Exception:
        return ""

    # 1. Claude.ai direct prompt format (from claude.txt)
    if "prompt" in data and isinstance(data["prompt"], str):
        # Check if it's the simple format or needs split (Legacy)
        prompt = data["prompt"]
        if "\n\nHuman:" in prompt:
            parts = prompt.split("\n\nHuman:")
            last_part = parts[-1].split("\n\nAssistant:")[0]
            return last_part.strip()
        return prompt

    # 2. ChatGPT/Generic messages format
    messages = data.get("messages", [])
    if isinstance(messages, list) and len(messages) > 0:
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
        
        if text_chunks:
            return " ".join(text_chunks).strip()

    # 3. Claude Web UI format (chat_messages)
    if "text" in data and isinstance(data["text"], str):
        return data["text"]

    # 4. Anthropic API format (Messages API)
    anthropic_messages = data.get("messages", [])
    if isinstance(anthropic_messages, list):
        text_chunks = []
        for m in anthropic_messages:
            if m.get("role") == "user":
                content = m.get("content")
                if isinstance(content, str):
                    text_chunks.append(content)
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_chunks.append(part.get("text", ""))
        if text_chunks:
            return " ".join(text_chunks).strip()

    return ""


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
        # Determine filename if possible, else default
        filename = "upload.pdf" 
        if "pdf" in content_type.lower():
            filename = "upload.pdf"
        elif "image" in content_type.lower():
            filename = "upload.png"

        files = {
            "file": (filename, content)
        }

        response = requests.post(
            "http://localhost:8000/scan-file",
            files=files,
            timeout=30
        )

        data = response.json()
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
        if hasattr(value, "filename") and value.filename:
            filename = value.filename
            content = value.content

            print("MULTIPART FILE:", filename, len(content))

            # If it's a binary file (PDF, Image), use scan-file
            if filename.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff')):
                try:
                    files = {"file": (filename, content)}
                    response = requests.post(
                        "http://localhost:8000/scan-file",
                        files=files,
                        timeout=30
                    )
                    decision = response.json().get("decision")
                    if decision == "block":
                        flow.response = http.Response.make(
                            403,
                            b"Blocked: Sensitive data in file",
                            {"Content-Type": "text/plain"}
                        )
                        return
                except Exception as e:
                    print("Multipart file scan error:", e)
            else:
                # Handle text-based files
                try:
                    text = content.decode("utf-8", errors="ignore")
                except:
                    text = ""

                if text:
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
        # CLAUDE uses claudeusercontent.com
        # -----------------------
        is_blob_storage = any(h in host for h in ["oaiusercontent.com", "claudeusercontent.com"])
        is_potential_file = method in ["PUT", "POST"] and ("anthropic.com" in host or "claude.ai" in host)
        
        # Only treat as raw file if NOT JSON and NOT Multipart
        if (is_blob_storage or is_potential_file) and "application/json" not in content_type and "multipart/form-data" not in content_type and "text/plain" not in content_type:
            handle_raw_file_upload(flow)
            if flow.response: # If blocked
                return
            # If not blocked, we might still want to check if it's a text request later, 
            # but usually raw uploads are separate from API calls.
            # However, for safety, let's only return if we actually handled it.
            if is_blob_storage:
                return

        # 2. MULTIPART FILE (fallback)
        if "multipart/form-data" in content_type:
            handle_multipart_upload(flow)
            return

        # 3. TEXT REQUESTS in LLM
        if "/backend-api/conversation" in path or "/backend-api/f/conversation" in path or "/v1/" in path or "/api/organizations/" in path or "/chat_conversations/" in path:
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