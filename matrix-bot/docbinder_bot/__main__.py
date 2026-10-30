from __future__ import annotations

import asyncio
from html import escape
import os
import re
import time

import httpx
from nio import AsyncClient, AsyncClientConfig, InviteMemberEvent, MatrixRoom, RoomMessageText, RoomSendResponse

from .store import ConversationStore
from .workflow import backend_payload, help_text, parse_request_block


HOMESERVER = os.getenv("MATRIX_HOMESERVER", "http://synapse:8008")
USER_ID = os.getenv("MATRIX_USER_ID", "@docbinder:klinikum.example")
PASSWORD = os.environ["MATRIX_PASSWORD"]
BACKEND = os.getenv("BACKEND_URL", "http://backend:8000")
ALLOWED = {item.strip() for item in os.getenv(
    "ALLOWED_MATRIX_USERS", "@lena.hofer:klinikum.example"
).split(",") if item.strip()}
STARTED_MS = int(time.time() * 1000)
store = ConversationStore()


class DocBinderBot:
    def __init__(self):
        config = AsyncClientConfig(store_sync_tokens=True)
        self.client = AsyncClient(HOMESERVER, USER_ID, store_path="/data/nio", config=config)

    async def send(self, room_id: str, message: str) -> bool:
        formatted = escape(message)
        formatted = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", formatted)
        formatted = re.sub(r"`(.+?)`", r"<code>\1</code>", formatted)
        formatted = formatted.replace("\n", "<br>")
        response = await self.client.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={
                "msgtype": "m.text", "body": message,
                "format": "org.matrix.custom.html", "formatted_body": formatted,
            },
        )
        return isinstance(response, RoomSendResponse)

    async def invite(self, room: MatrixRoom, event: InviteMemberEvent) -> None:
        if event.sender in ALLOWED:
            await self.client.join(room.room_id)

    async def message(self, room: MatrixRoom, event: RoomMessageText) -> None:
        if event.sender == USER_ID or event.server_timestamp < STARTED_MS - 5_000:
            return
        message = event.body.strip()
        if event.sender not in ALLOWED:
            if message.startswith("!") or message.startswith("/request-document"):
                await self.send(room.room_id, "You are not authorized to create DocBinder requests.")
            return
        if message in {"!help", "/help"}:
            await self.send(room.room_id, help_text())
            return
        if message in {"!request-document", "/request-document"}:
            store.save(room.room_id, event.sender, "awaiting_block", {})
            await self.send(room.room_id, help_text())
            return
        if message == "!cancel":
            store.clear(room.room_id, event.sender)
            await self.send(room.room_id, "Request creation cancelled.")
            return
        if message == "!requests":
            await self.list_requests(room.room_id)
            return
        if message.startswith("!revoke "):
            await self.revoke(room.room_id, message.split(maxsplit=1)[1])
            return

        state = store.get(room.room_id, event.sender)
        if not state:
            return
        step, data = state
        if step == "confirm":
            if message.casefold() != "confirm":
                await self.send(room.room_id, "Reply **confirm** to create the request, or `!cancel`.")
                return
            await self.confirm(room.room_id, event.sender, data)
            return
        parsed, response = parse_request_block(message)
        if parsed is not None:
            store.save(room.room_id, event.sender, "confirm", parsed)
        await self.send(room.room_id, response)

    async def confirm(self, room_id: str, user_id: str, data: dict) -> None:
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                response = await http.post(f"{BACKEND}/api/requests", json=backend_payload(room_id, user_id, data))
                response.raise_for_status()
                created = response.json()
            store.clear(room_id, user_id)
            warning = "\n" + "\n".join(f"⚠️ {item}" for item in created.get("warnings", [])) if created.get("warnings") else ""
            await self.send(room_id, f"✅ Request **{created['id']}** was created and the privacy-safe invitation was sent.{warning}")
        except httpx.HTTPError as exc:
            await self.send(room_id, f"DocBinder could not create the request. Please retry. ({type(exc).__name__})")

    async def list_requests(self, room_id: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=10) as http:
                response = await http.get(f"{BACKEND}/api/requests", params={"limit": 5})
                response.raise_for_status()
                requests = response.json()
            if not requests:
                await self.send(room_id, "No DocBinder requests yet.")
                return
            lines = ["**Recent DocBinder requests**"]
            lines += [f"- {item['id']} — {item['recipient_name']} — {item['status']}" for item in requests]
            await self.send(room_id, "\n".join(lines))
        except httpx.HTTPError:
            await self.send(room_id, "Could not load requests from DocBinder.")

    async def revoke(self, room_id: str, request_id: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=10) as http:
                response = await http.post(f"{BACKEND}/api/requests/{request_id}/revoke")
                response.raise_for_status()
            await self.send(room_id, f"Request **{request_id}** is revoked.")
        except httpx.HTTPStatusError as exc:
            await self.send(room_id, f"Could not revoke that request ({exc.response.status_code}).")

    async def notification_loop(self) -> None:
        await asyncio.sleep(5)
        while True:
            try:
                async with httpx.AsyncClient(timeout=10) as http:
                    response = await http.get(f"{BACKEND}/api/internal/matrix-notifications")
                    response.raise_for_status()
                    for item in response.json():
                        destination = item["destination"]
                        if destination.startswith("!") and await self.send(destination, item["body"]):
                            delivered = await http.post(f"{BACKEND}/api/internal/matrix-notifications/{item['id']}/delivered")
                            delivered.raise_for_status()
            except (httpx.HTTPError, OSError):
                pass
            await asyncio.sleep(5)

    async def run(self) -> None:
        while True:
            login = await self.client.login(PASSWORD, device_name="DocBinder Bot")
            if getattr(login, "access_token", None):
                break
            print("Matrix login is not ready; retrying in 10 seconds.", flush=True)
            await asyncio.sleep(10)
        self.client.add_event_callback(self.invite, InviteMemberEvent)
        self.client.add_event_callback(self.message, RoomMessageText)
        notifications = asyncio.create_task(self.notification_loop())
        try:
            await self.client.sync_forever(timeout=30_000, full_state=True)
        finally:
            notifications.cancel()
            await self.client.close()


if __name__ == "__main__":
    asyncio.run(DocBinderBot().run())
