#dlpProxy.py
from mitmproxy import http
import requests
import json
import datetime
import hashlib
import re
import base64

BASE64_PDF_PATTERN = re.compile(rb'JVBERi0xL[A-Za-z0-9+/=]+')

#Added logging because MITMProxy isnt fun
LOG_FILE = "dlpProxy.log"

def log(message):

    timestamp = datetime.datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    line = f"[{timestamp}] {message}"

    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

#Tryna make the code cleaner - I think this should be more manageable.
#Not using because provider handling is too complex atp
#Split API to /scan-file/openai and /scan-file/claude, /scan is used by scan_text()
SCAN_API = "http://localhost:8000/scan" #Change to server IP - currently runs in localhost

OPENAI_FILE_API = "http://localhost:8000/scan-file/openai"

CLAUDE_FILE_API = "http://localhost:8000/scan-file/claude"

#Functions Split for Provider Detection:
def is_openai_request(host):
    return (
        "chatgpt.com" in host
        or "openai.com" in host
        or "oaiusercontent.com" in host
    )


def is_claude_request(host):
    return (
        "claude.ai" in host
        or "anthropic.com" in host
        or "claudeusercontent.com" in host
    )

def is_perplexity_request(host):
    return (
        "perplexity.ai" in host
        or "pplx" in host
        or "amazonaws.com" in host
    )


#Block Response
def block_response(flow, reason):

    flow.response = http.Response.make(
        403,
        reason.encode(),
        {"Content-Type": "text/plain"}
    )



#Check content and block logic for OpenAI uploads
def handle_openai_upload(flow):
    content = flow.request.raw_content
    if flow.response:
        return
    if not content:
        return
    if not content.startswith(b"%PDF"):
        log("Skipping non-PDF OpenAI upload")
        return
    log(f"OPENAI PDF: {len(content)}")
    files = {
        "file": ("upload.pdf", content)
    }
    response = requests.post(
        OPENAI_FILE_API,
        files=files,
        timeout=90
    )
    decision = response.json().get("decision")
    log(f"OPENAI FILE DECISION: {decision}")
    if decision == "block":
        block_response(
            flow,
            "Blocked: Sensitive OpenAI upload"
        )


#Same for claude
import io
import os
from multipart import MultipartParser, parse_options_header


def handle_perplexity_upload(flow):
    handle_claude_upload(flow)

def handle_claude_upload(flow):
    try:
        content_type_header = flow.request.headers.get(
            "Content-Type",
            ""
        )
        content_type, options = parse_options_header(
            content_type_header
        )
        if content_type != "multipart/form-data":
            log("NOT MULTIPART")
            return
        boundary = (
            options.get(b"boundary")
            or options.get("boundary")
        )
        if not boundary:
            log("NO BOUNDARY FOUND")
            return
        raw_body = flow.request.get_content()
        stream = io.BytesIO(raw_body)
        parser = MultipartParser(stream, boundary)
        for part in parser:
            # Skip non-file fields
            if not part.filename:
                continue
            try:
                # SAFEST extraction path
                if hasattr(part, "raw"):
                    file_bytes = part.raw
                elif hasattr(part, "file"):
                    part.file.seek(0)
                    file_bytes = part.file.read()
                else:
                    log("CANNOT READ FILE BYTES")
                    continue
                if not file_bytes:

                    log("EMPTY FILE")
                    continue
                filename = os.path.basename(
                    part.filename
                )
                log(
                    f"CLAUDE FILE DETECTED: "
                    f"{filename} "
                    f"{len(file_bytes)} bytes"
                )
                # Optional MIME detection
                is_pdf = file_bytes.startswith(b"%PDF")
                if is_pdf:
                    log("PDF DETECTED")
                # Send clean bytes to scanner
                files = {
                    "file": (
                        filename,
                        file_bytes,
                        "application/octet-stream"
                    )
                }
                response = requests.post(
                    CLAUDE_FILE_API,
                    files=files,
                    timeout=120
                )
                log(
                    f"SCAN STATUS: "
                    f"{response.status_code}"
                )
                log(
                    f"SCAN RESPONSE: "
                    f"{response.text}"
                )
                result = response.json()
                decision = result.get("decision")
                log(f"DECISION: {decision}")
                if decision == "block":
                    flow.response = http.Response.make(
                        403,
                        b"Blocked: Sensitive file detected",
                        {"Content-Type": "text/plain"}
                    )
                    return
            except Exception as file_error:
                log(
                    f"FILE PROCESSING ERROR: "
                    f"{file_error}"
                )
        # Cleanup temp handles
        try:
            for p in parser.parts():
                p.close()
        except Exception:
            pass
    except Exception as e:
        log(f"CLAUDE MULTIPART ERROR: {e}")

#I've lost the plot, idk if this is being used. - It is.
# SCAN TEXT - CHECK server.py 
def scan_text(text):
    try:
        response = requests.post(
            SCAN_API,
            json={"text": text},
            timeout=20
        )
        return response.json().get("decision")
    except Exception as e:
        log(f"Scan error: {e}")
        return "allow"

#EXTRACTION FROM JSON - claude
def extract_claude_prompt(data):

    if (
        "prompt" in data
        and isinstance(data["prompt"], str)
    ):
        return data["prompt"]

    if (
        "text" in data
        and isinstance(data["text"], str)
    ):
        return data["text"]

    return ""
    
#EXTRACTION FROM JSON -OPNAI
def extract_openai_prompt(data):

    if not isinstance(data, dict):
        return ""
    messages = data.get("messages", [])
    if not isinstance(messages, list):
        return ""
    text_chunks = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        # Detect role
        role = (
            m.get("role")
            or m.get("author", {}).get("role")
        )
        if role != "user":
            continue
        content_obj = m.get("content")
        if isinstance(content_obj, dict):
            parts = content_obj.get("parts", [])
            if isinstance(parts, list):
                for p in parts:
                    if isinstance(p, str):
                        text_chunks.append(p)
                    elif isinstance(p, dict):
                        text = p.get("text")
                        if isinstance(text, str):
                            text_chunks.append(text)
        elif isinstance(content_obj, str):
            text_chunks.append(content_obj)
        elif isinstance(content_obj, list):
            for item in content_obj:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str):
                        text_chunks.append(text)
    return "\n".join(text_chunks).strip()

def extract_perplexity_prompt(data):

    if (
        "query_str" in data
        and isinstance(data["query_str"], str)
    ):
        return data["query_str"]

    return ""

# MAIN ENTRY
def request(flow: http.HTTPFlow):
    try:
        host = flow.request.pretty_host
        path = flow.request.path
        method = flow.request.method
        content_type = flow.request.headers.get("content-type","")
        # OPENAI
        if is_openai_request(host):
            # RAW PDF uploads
            if ("oaiusercontent.com" in host
                and method in ["PUT", "POST"]):
                handle_openai_upload(flow)
                return
            # OpenAI prompt requests
            if ("/backend-api/f/conversation" in path
                or "/v1/" in path):

                flow.request.decode()
                raw = flow.request.text or ""
                try:
                    data = json.loads(raw)
                except:
                    return
                content = extract_openai_prompt(data)
                if not content:
                    return
                decision = scan_text(content)
                log(f"OPENAI TEXT: {decision}")
                if decision == "block":
                    block_response(flow,
                        "Blocked: Sensitive OpenAI text")

                return
        # CLAUDE
        elif is_claude_request(host):
            log(f"CLAUDE PATH: {path}")
            if "/completion" in path:
                log(f"CLAUDE TEXT")

                flow.request.decode()

                raw = flow.request.text or ""

                try:
                    data = json.loads(raw)
                except:
                    return

                content = extract_claude_prompt(data)

                if not content:
                  return

                decision = scan_text(content)

                log(f"CLAUDE TEXT DECISION: {decision}")

                if decision == "block":

                    block_response(
                        flow,
                        "Blocked: Sensitive Claude text"
                    )

                return
            elif "/wiggle/upload-file" in path:
                    log(f"CLAUDE FILE")
                    handle_claude_upload(flow)
                    return
        # PERPLEXITY
        elif is_perplexity_request(host):

            log(f"PERPLEXITY PATH: {path}")

            # TEXT REQUESTS
            if (
                method == "POST"
                and "application/json" in content_type
            ):

                log("PERPLEXITY TEXT")

                flow.request.decode()

                raw = flow.request.text or ""

                try:
                    data = json.loads(raw)
                except Exception as e:
                    log(f"PPLX JSON ERROR: {e}")
                    return

                content = extract_perplexity_prompt(data)

                if not content:
                    return

                decision = scan_text(content)

                log(f"PERPLEXITY TEXT DECISION: {decision}")

                if decision == "block":

                    block_response(
                        flow,
                        "Blocked: Sensitive Perplexity text"
                    )

                return
    except Exception as e:
        log(f"Error: {format(e)}")