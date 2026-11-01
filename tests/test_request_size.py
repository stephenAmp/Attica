# import requests

# url = "https://accralife.app/api/login"

# payload = {
#     "handle": "user@example.com",
#     "password": "A" * 70000 #68kb
#     # "password": "A" * 1_073_741_824 #1Gib
# }

# response = requests.post(url, json=payload)

# print(response.status_code)
# print(response.text)

import httpx

url = "http://localhost:8000/auth/login"

headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://accralife.app",
    "Referer": "https://accralife.app/",
}

payload = {
    "handle": "user@example.com",
    "password": "A" * 70000 #68kb
}

timeout = httpx.Timeout(
    30.0,
    write=60.0
)

try:
    response = httpx.post(
        url,
        json=payload,
        headers=headers,
        timeout=timeout
    )
    print(response.status_code, response.text)

except httpx.WriteTimeout:
    print("Timed out while sending the request body")

print("Status:", response.status_code)
print("Response:", response.text)