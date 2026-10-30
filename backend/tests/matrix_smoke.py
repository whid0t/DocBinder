"""Exercise the live Synapse/Matrix-bot path from inside the Compose network."""

import time
from urllib.parse import quote
import uuid
import os

import httpx


BASE = "http://synapse:8008/_matrix/client/v3"
DOCTOR = "@lena.hofer:klinikum.example"
BOT = "@docbinder:klinikum.example"


def main() -> None:
    login = httpx.post(f"{BASE}/login", json={
        "type": "m.login.password",
        "identifier": {"type": "m.id.user", "user": DOCTOR},
        "password": os.getenv("DOCTOR_MATRIX_PASSWORD", "docbinder-doctor-demo"),
        "initial_device_display_name": "DocBinder smoke test",
    }, timeout=15)
    login.raise_for_status()
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = httpx.post(f"{BASE}/createRoom", headers=headers, json={
        "name": "DocBinder Demo",
        "topic": "Secure external clinical document requests",
        "preset": "private_chat",
        "invite": [BOT],
        "is_direct": True,
    }, timeout=15)
    created.raise_for_status()
    room_id = created.json()["room_id"]
    encoded_room = quote(room_id, safe="")
    time.sleep(2)

    initial = httpx.get(f"{BASE}/sync", headers=headers, params={"timeout": 0}, timeout=15)
    initial.raise_for_status()
    since = initial.json()["next_batch"]
    sent = httpx.put(
        f"{BASE}/rooms/{encoded_room}/send/m.room.message/{uuid.uuid4()}",
        headers=headers,
        json={"msgtype": "m.text", "body": "!help"},
        timeout=15,
    )
    sent.raise_for_status()

    for _ in range(10):
        synced = httpx.get(
            f"{BASE}/sync", headers=headers, params={"since": since, "timeout": 2000}, timeout=5
        )
        synced.raise_for_status()
        payload = synced.json()
        since = payload["next_batch"]
        events = payload.get("rooms", {}).get("join", {}).get(room_id, {}).get("timeline", {}).get("events", [])
        if any(event.get("sender") == BOT and "DocBinder request format" in event.get("content", {}).get("body", "") for event in events):
            print(f"OK: bot joined and replied in {room_id}")
            return
    raise RuntimeError("The bot did not reply to !help")


if __name__ == "__main__":
    main()
