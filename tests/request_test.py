import os
import uuid
import httpx

tenant_id = os.environ["ATTICA_TENANT_ID"]
api_key = os.environ["ATTICA_API_KEY"]

response = httpx.post(
    f"http://localhost:8000/tenants/{tenant_id}/outcomes",
    headers={
        "X-Attica-API-Key": api_key,
    },
    json={
        "event_id": str(uuid.uuid4()),
        "trace_id": "22222222-2222-4222-8222-222222222222",
        "name": "extraction_corrected",
        "occurred_at": "2026-11-22T10:00:00Z",
    },
    timeout=10,
)

print(response.status_code, response.json())