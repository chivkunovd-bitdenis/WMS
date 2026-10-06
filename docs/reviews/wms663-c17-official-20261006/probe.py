"""One bounded public-document fetch route; executed on GitHub only."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

OUT = Path(os.environ["C17_OUTPUT"])
OUT.mkdir(parents=True, exist_ok=True)
URL = "https://docs.ozon.ru/api/seller/swagger.json"
PATHS = ["/v6/fbs/posting/product/exemplar/set", "/v5/fbs/posting/product/exemplar/status"]
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None
opener = urllib.request.build_opener(NoRedirect)
meta = {"fetched_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "source_url": URL, "runner": "GitHub ubuntu-24.04", "probe_sha": os.environ.get("GITHUB_SHA"), "chain": [], "result": "UNKNOWN"}
seen = set()
try:
    url = URL
    for hop in range(6):
        if url in seen:
            raise ValueError("redirect loop")
        seen.add(url)
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in {"docs.ozon.ru", "st.ozone.ru"} or parsed.username or parsed.password:
            raise ValueError("redirect outside official public-document allowlist; stopped")
        try:
            response = opener.open(urllib.request.Request(url, headers={"User-Agent": "WMS-C17-public-document-verification/1.0", "Accept": "application/json"}), timeout=25)
        except urllib.error.HTTPError as error:
            response = error
        entry = {"url": url, "http_status": response.code, "content_type": response.headers.get("Content-Type"), "location": response.headers.get("Location"), "date": response.headers.get("Date"), "etag": response.headers.get("ETag"), "last_modified": response.headers.get("Last-Modified")}
        meta["chain"].append(entry)
        if response.code in {301,302,303,307,308}:
            response.close()
            location = entry["location"]
            if not location:
                raise ValueError("redirect missing Location")
            url = urllib.parse.urljoin(url, location)
            continue
        raw = response.read(12 * 1024 * 1024 + 1)
        response.close()
        if len(raw) > 12 * 1024 * 1024:
            raise ValueError("public asset exceeded 12 MiB bound")
        meta.update({"final_url": url, "body_bytes": len(raw), "body_sha256": hashlib.sha256(raw).hexdigest()})
        if entry["http_status"] != 200:
            (OUT / "unavailable-response.txt").write_bytes(raw[:32768])
            raise ValueError("non-200 document response")
        try:
            document = json.loads(raw)
        except ValueError:
            (OUT / "unavailable-response.txt").write_bytes(raw[:32768])
            raise ValueError("response is not JSON schema")
        selected = {path: document["paths"][path] for path in PATHS}
        schemas = document["components"]["schemas"]
        refs = set()
        def collect(value):
            if isinstance(value, dict):
                ref = value.get("$ref", "")
                if ref.startswith("#/components/schemas/"):
                    refs.add(ref.rsplit("/", 1)[1])
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)
        collect(selected)
        kept = {}
        while refs - kept.keys():
            name = sorted(refs - kept.keys())[0]
            kept[name] = schemas[name]
            collect(kept[name])
        excerpt = {"openapi": document.get("openapi"), "info": document.get("info"), "paths": selected, "components": {"schemas": kept}}
        data = (json.dumps(excerpt, ensure_ascii=False, indent=2) + "\n").encode()
        (OUT / "official-schema-excerpt.json").write_bytes(data)
        meta.update({"result": "OFFICIAL_SCHEMA_FETCHED_NOT_ACCEPTANCE", "excerpt_sha256": hashlib.sha256(data).hexdigest(), "excerpt_bytes": len(data)})
        break
    else:
        raise ValueError("redirect limit reached")
except Exception as error:
    meta["failure"] = str(error)
finally:
    (OUT / "fetch-metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
