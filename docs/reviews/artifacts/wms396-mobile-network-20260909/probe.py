"""One synthetic request, with no retries, tokens, redirects, or TLS bypass."""
import datetime
import hashlib
import json
import re
import httpx

url = "https://mobile.api.crpt.ru/mobile/check"
result = {
    "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "url": url,
    "method": "POST",
    "request_json": {"code": "WMS396_SYNTHETIC_INVALID_CODE"},
    "tls_verify": True,
    "follow_redirects": False,
    "httpx_version": httpx.__version__,
}
try:
    with httpx.Client(timeout=20.0, verify=True, follow_redirects=False) as client:
        response = client.post(url, json=result["request_json"])
    result["outcome"] = "http_response"
    result["status_code"] = response.status_code
    allowed_headers = {"content-type", "content-length", "date", "server", "via", "retry-after", "x-request-id"}
    result["response_headers"] = {key: value for key, value in response.headers.items() if key.lower() in allowed_headers}
    result["response_bytes"] = len(response.content)
    result["response_sha256"] = hashlib.sha256(response.content).hexdigest()
    try:
        body = response.json()
        allowed_fields = {"code", "error", "errorCode", "errorMessage", "message", "success", "status"}
        result["body_allowlist"] = {key: (value[:500] if isinstance(value, str) else value) for key, value in body.items() if key in allowed_fields and (value is None or isinstance(value, (str, int, float, bool)))} if isinstance(body, dict) else {}
        result["body_format"] = "json"
    except ValueError:
        result["body_format"] = "empty" if not response.content else "non_json"
except Exception as error:
    result["outcome"] = "client_exception"
    result["exception_type"] = type(error).__name__
    result["exception_message"] = re.sub(r"(https?://)[^/@ ]+:[^/@ ]+@", r"\1[redacted]@", str(error))[:500]
result["finished_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
print(json.dumps(result, ensure_ascii=False))
