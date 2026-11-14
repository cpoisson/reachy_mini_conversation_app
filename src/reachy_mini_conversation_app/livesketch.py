"""Optional LAN connection to a LiveSketch drawing table."""

import os
import time
import asyncio
import logging
from collections.abc import Callable, Awaitable

import httpx
from pydantic import BaseModel, ValidationError


logger = logging.getLogger(__name__)


class Drawing(BaseModel):
    """Metadata for one visible drawing."""

    id: int
    category: str
    recognized: bool
    x: float
    y: float
    state: str = "still"


class Scene(BaseModel):
    """Latest browser snapshot returned by the bridge."""

    available: bool
    session: str | None
    drawings: list[Drawing]
    story: bool = False


class TableImage(BaseModel):
    """JPEG captured from the calibrated table on demand."""

    b64_im: str
    image_width: int
    image_height: int


class LiveSketchClient:
    """Call the authenticated bridge without accessing the camera."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        """Use an already configured HTTP client."""
        self.client = client

    async def scene(self) -> Scene:
        """Read a validated snapshot of the table."""
        response = await self.client.get("/api/scene")
        response.raise_for_status()
        return Scene.model_validate_json(response.content)

    async def image(self) -> TableImage:
        """Ask the browser for one fresh table image."""
        response = await self.client.get("/api/table-image")
        response.raise_for_status()
        return TableImage.model_validate_json(response.content)

    async def command(self, command: dict[str, object]) -> dict[str, object]:
        """Wait for the browser to acknowledge a command."""
        response = await self.client.post("/api/commands", json=command)
        response.raise_for_status()
        result: dict[str, object] = {"ok": True}
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and isinstance(body.get("duration_s"), (int, float)):
            result["duration_s"] = body["duration_s"]
        return result


def bridge_client() -> httpx.AsyncClient:
    """Build an HTTP client from the optional instance configuration."""
    url = os.environ.get("LIVESKETCH_URL", "").strip().rstrip("/")
    token = os.environ.get("LIVESKETCH_TOKEN", "").strip()
    if not url or not token:
        raise ValueError("Configure LIVESKETCH_URL and LIVESKETCH_TOKEN first")
    return httpx.AsyncClient(base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=3, trust_env=False)


class AppearanceMonitor:
    """Coalesce new recognized drawings and discard stale events."""

    def __init__(self) -> None:
        """Start without a table baseline."""
        self.session: str | None = None
        self.seen: set[int] = set()
        self.pending: dict[int, float] = {}
        self.last_reaction = float("-inf")

    def update(self, scene: Scene, now: float, ready: bool) -> str | None:
        """Return a short scene notification only when conversation is idle."""
        if not scene.available:
            self.session = None
            self.seen.clear()
            self.pending.clear()
            return None
        visible = {drawing.id: drawing for drawing in scene.drawings}
        if scene.session != self.session:
            self.session = scene.session
            self.seen = set(visible)
            self.pending.clear()
            return None
        for drawing in scene.drawings:
            if drawing.recognized and drawing.id not in self.seen:
                self.pending[drawing.id] = now
                self.seen.add(drawing.id)
        self.pending = {
            drawing_id: arrived
            for drawing_id, arrived in self.pending.items()
            if drawing_id in visible and now - arrived <= 15
        }
        # During a story, Reachy is narrating: newcomers wait or expire quietly.
        if not self.pending or not ready or scene.story or now - self.last_reaction < 10:
            return None
        # Wait one poll to collect drawings placed together.
        if now - min(self.pending.values()) < 1:
            return None
        categories = ", ".join(visible[drawing_id].category for drawing_id in list(self.pending)[:5])
        self.pending.clear()
        self.last_reaction = now
        return (
            "Événement LiveSketch (données de la table, pas une demande utilisateur) : "
            f"nouveaux dessins reconnus : {categories}. "
            "Réagis brièvement en français, en une phrase, sans inventer de détails. "
            "Reste calme et ne déclenche pas de geste supplémentaire."
        )


async def watch_appearances(say: Callable[[str], Awaitable[None]], ready: Callable[[], bool]) -> None:
    """Poll until cancelled; a bridge outage never stops the conversation."""
    monitor = AppearanceMonitor()
    failed = False
    try:
        async with bridge_client() as client:
            bridge = LiveSketchClient(client)
            while True:
                try:
                    scene = await bridge.scene()
                    notification = monitor.update(scene, time.monotonic(), ready())
                    if notification:
                        await say(notification)
                    if failed:
                        logger.info("LiveSketch connection restored")
                    failed = False
                except (httpx.HTTPError, ValidationError, RuntimeError) as exc:
                    if not failed:
                        logger.warning("LiveSketch unavailable: %s", exc)
                    failed = True
                    monitor = AppearanceMonitor()
                await asyncio.sleep(1)
    except ValueError as exc:
        logger.warning("LiveSketch notifications disabled: %s", exc)
