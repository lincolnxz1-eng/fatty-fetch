"""Local smoke test: python smoke_test.py [force-metadata-client]. Simulates Render by forcing tv_embedded/android_vr as the metadata client."""
import sys, app
from fastapi.testclient import TestClient
if len(sys.argv) > 1: app.CLIENT_CHAINS = [["tv_embedded", "android_vr"], ["android_vr"]]
c = TestClient(app.app)
for v in ("dfET5tfvnxw", "IiUA53Sw2fU"):
    j = c.post("/fetch", json={"url": "https://www.youtube.com/watch?v=" + v}).json()
    print(v, j.get("source"), len(j.get("transcript") or ""), j.get("language"), j.get("caption_error"), (j.get("title") or "")[:50], j.get("error"))
