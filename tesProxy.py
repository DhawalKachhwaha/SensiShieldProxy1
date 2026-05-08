from mitmproxy import http
import requests
import json

SCAN_API = "http://localhost:8000/scan"

def extract_prompt(data):
    try:
        messages = data.get("messages", [])
        parts = []

        for msg in messages:
            role = msg.get("author", {}).get("role")

            if role != "user":
                continue

            content = msg.get("content", {})
            msg_parts = content.get("parts", [])

            for p in msg_parts:
                if isinstance(p, str):
                    parts.append(p)

        return " ".join(parts)

    except Exception as e:
        print("Extract error:", e)
        return ""

def request(flow: http.HTTPFlow):

    try:
        host = flow.request.pretty_host
        path = flow.request.path

        # ONLY inspect actual ChatGPT prompt requests
        if (
            "chatgpt.com" not in host or
            "/backend-api/f/conversation" not in path
        ):
            return

        flow.request.decode()

        raw = flow.request.text

        if not raw:
            return

        data = json.loads(raw)

        prompt = extract_prompt(data)

        print("\nPROMPT:", prompt)

        if not prompt:
            return

        response = requests.post(
            SCAN_API,
            json={"text": prompt},
            timeout=5
        )

        result = response.json()

        decision = result.get("decision", "allow")

        print("Decision:", decision)

        if decision == "block":
            flow.response = http.Response.make(
                403,
                b"Blocked: Sensitive data detected",
                {"Content-Type": "text/plain"}
            )

    except Exception as e:
        print("Proxy error:", e)