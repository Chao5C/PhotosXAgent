import json
import time
import urllib.request
from pathlib import Path

login = urllib.request.Request(
    "http://127.0.0.1:8000/api/auth/login",
    data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
    headers={"Content-Type": "application/json"},
)
token = json.loads(urllib.request.urlopen(login).read().decode())["data"]["access_token"]

boundary = "----PhotosXBoundary"
file_bytes = Path("data/uploads/_sample.jpg").read_bytes()
parts = [
    f"--{boundary}\r\n".encode(),
    b'Content-Disposition: form-data; name="files"; filename="sample.jpg"\r\n',
    b"Content-Type: image/jpeg\r\n\r\n",
    file_bytes,
    f"\r\n--{boundary}--\r\n".encode(),
]
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/photos/upload",
    data=b"".join(parts),
    method="POST",
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    },
)
print("UPLOAD", urllib.request.urlopen(req).read().decode())

time.sleep(2)
stats = urllib.request.Request(
    "http://127.0.0.1:8000/api/photos/stats",
    headers={"Authorization": f"Bearer {token}"},
)
print("STATS", urllib.request.urlopen(stats).read().decode())

photos = urllib.request.Request(
    "http://127.0.0.1:8000/api/photos",
    headers={"Authorization": f"Bearer {token}"},
)
print("PHOTOS", urllib.request.urlopen(photos).read().decode()[:800])

chat = urllib.request.Request(
    "http://127.0.0.1:8000/api/chat",
    data=json.dumps({"message": "我有多少张照片"}).encode(),
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
)
print("CHAT", urllib.request.urlopen(chat).read().decode())
