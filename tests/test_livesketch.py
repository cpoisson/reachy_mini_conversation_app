import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

import reachy_mini_conversation_app.livesketch as module
from reachy_mini_conversation_app.tools import (
    livesketch_act,
    livesketch_say,
    livesketch_look,
    livesketch_get_scene,
    livesketch_stop_story,
    livesketch_tell_story,
)
from reachy_mini_conversation_app.livesketch import Scene, AppearanceMonitor, watch_appearances


def snapshot(*ids, available=True, session="table-1", category="boat", recognized=True, story=False):
    """Snapshot."""
    return Scene(
        available=available,
        session=session,
        story=story,
        drawings=[{"id": i, "category": category, "recognized": recognized, "x": 0.2, "y": 0.3} for i in ids],
    )


def test_appearance_baseline_coalescing_reclassification_and_cooldown():
    """Appearance baseline coalescing reclassification and cooldown."""
    monitor = AppearanceMonitor()
    assert monitor.update(snapshot(1), 0, True) is None
    assert monitor.update(snapshot(1, 2, recognized=False), 1, True) is None
    assert monitor.update(snapshot(1, 2), 2, True) is None
    notice = monitor.update(snapshot(1, 2, 3), 3, True)
    assert notice is not None and "boat, boat" in notice
    assert monitor.update(snapshot(1, 2, 3, category="vehicle"), 4, True) is None
    assert monitor.update(snapshot(1, 2, 3, 4), 5, True) is None
    assert monitor.update(snapshot(1, 2, 3, 4), 12, True) is None
    assert monitor.update(snapshot(1, 2, 3, 4), 13, True) is not None


def test_busy_removed_expired_and_reconnected_drawings_are_not_announced():
    """Busy removed expired and reconnected drawings are not announced."""
    monitor = AppearanceMonitor()
    monitor.update(snapshot(), 0, True)
    monitor.update(snapshot(1), 1, False)
    assert monitor.update(snapshot(1), 2, False) is None
    assert monitor.update(snapshot(), 3, True) is None
    monitor.update(snapshot(2), 4, False)
    assert monitor.update(snapshot(2), 20, True) is None
    monitor.update(snapshot(2, available=False), 21, True)
    assert monitor.update(snapshot(2, 3), 22, True) is None
    assert monitor.update(snapshot(1, session="new-tab"), 23, True) is None


@pytest.mark.asyncio
async def test_tools_auth_scene_and_acknowledged_commands(monkeypatch):
    """Tools auth scene and acknowledged commands."""
    received = []

    def handle(request):
        assert request.headers["Authorization"] == "Bearer test-token"
        received.append(request)
        if request.url.path == "/api/scene":
            return httpx.Response(200, json=snapshot(1).model_dump())
        return httpx.Response(200, json={"ok": True})

    def client():
        return httpx.AsyncClient(
            base_url="http://table:8765",
            headers={"Authorization": "Bearer test-token"},
            transport=httpx.MockTransport(handle),
        )

    for tool_module in (livesketch_get_scene, livesketch_say, livesketch_stop_story):
        monkeypatch.setattr(tool_module, "bridge_client", client)
    result = await livesketch_get_scene.LiveSketchGetScene()(None)
    assert result["drawings"][0]["category"] == "boat"
    assert await livesketch_say.LiveSketchSay()(None, drawing_id=1, text="Ohé !") == {"ok": True}
    assert await livesketch_stop_story.LiveSketchStopStory()(None) == {"ok": True}
    assert len(received) == 3
    assert '"drawing_id":1' in received[1].content.decode()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 404, 409, 503])
async def test_tool_rejection_never_claims_success(monkeypatch, status):
    """Tool rejection never claims success."""
    monkeypatch.setattr(
        livesketch_say,
        "bridge_client",
        lambda: httpx.AsyncClient(
            base_url="http://table:8765",
            transport=httpx.MockTransport(lambda request: httpx.Response(status)),
        ),
    )
    assert "error" in await livesketch_say.LiveSketchSay()(None, drawing_id=1, text="Bonjour")
    assert "error" in await livesketch_say.LiveSketchSay()(None, drawing_id=True, text="Bonjour")


@pytest.mark.asyncio
async def test_watcher_recovers_without_replaying_and_cancels(monkeypatch):
    """Watcher recovers without replaying and cancels."""
    calls = 0
    say = AsyncMock()
    recovered = asyncio.Event()

    def respond(request):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise httpx.ConnectError("bridge down", request=request)
        if calls >= 4:
            recovered.set()
        return httpx.Response(200, json=snapshot(1, 2).model_dump())

    original_sleep = asyncio.sleep

    async def short_sleep(delay):
        await original_sleep(0)

    monkeypatch.setattr(
        module,
        "bridge_client",
        lambda: httpx.AsyncClient(
            base_url="http://table:8765",
            transport=httpx.MockTransport(respond),
        ),
    )
    monkeypatch.setattr(module.asyncio, "sleep", short_sleep)
    task = asyncio.create_task(watch_appearances(say, lambda: True))
    await asyncio.wait_for(recovered.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    say.assert_not_called()


@pytest.mark.asyncio
async def test_look_returns_fresh_table_image(monkeypatch):
    """The look tool fetches an image only when explicitly called."""
    image = {"b64_im": "/9j/2Q==", "image_width": 480, "image_height": 225}
    requests = []

    def respond(request):
        requests.append(request.url.path)
        return httpx.Response(200, json=image)

    monkeypatch.setattr(
        livesketch_look,
        "bridge_client",
        lambda: httpx.AsyncClient(
            base_url="http://table:8765",
            transport=httpx.MockTransport(respond),
        ),
    )
    assert await livesketch_look.LiveSketchLook()(None) == image
    assert requests == ["/api/table-image"]


def test_no_spontaneous_reaction_while_a_story_plays():
    """Drawings placed during a story are not announced over the narration."""
    monitor = AppearanceMonitor()
    monitor.update(snapshot(1), 0, True)
    monitor.update(snapshot(1, 2, story=True), 1, True)
    assert monitor.update(snapshot(1, 2, story=True), 3, True) is None
    assert monitor.update(snapshot(1, 2), 4, True) is not None


@pytest.mark.asyncio
async def test_tell_story_sends_script_and_asks_to_narrate(monkeypatch):
    """The whole script reaches the bridge; success tells Reachy to narrate it."""
    import json

    bodies = []
    status = 200

    def respond(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(status, json={"ok": True, "id": "x", "duration_s": 12.5})

    monkeypatch.setattr(
        livesketch_tell_story,
        "bridge_client",
        lambda: httpx.AsyncClient(base_url="http://table:8765", transport=httpx.MockTransport(respond)),
    )
    tool = livesketch_tell_story.LiveSketchTellStory()
    scenes = [{"narration": "Il était une fois un bateau.", "lines": [{"drawing_id": 1, "text": "Ohé !"}]}]
    result = await tool(None, title="Le bateau", scenes=scenes)
    assert result["ok"] is True and result["duration_s"] == 12.5 and "aloud" in result["next"]
    assert bodies[-1] == {"action": "story", "story": {"title": "Le bateau", "scenes": scenes}}
    status = 404
    assert "left the table" in (await tool(None, scenes=scenes))["error"]
    assert "error" in await tool(None, scenes=[])


@pytest.mark.asyncio
async def test_act_sends_motion_and_reports_refusals(monkeypatch):
    """A valid action reaches the screen; a refused one is never claimed."""
    import json

    bodies = []
    reply = httpx.Response(200, json={"ok": True, "id": "x"})

    def respond(request):
        bodies.append(json.loads(request.content))
        return reply

    monkeypatch.setattr(
        livesketch_act,
        "bridge_client",
        lambda: httpx.AsyncClient(base_url="http://table:8765", transport=httpx.MockTransport(respond)),
    )
    tool = livesketch_act.LiveSketchAct()
    assert await tool(None, drawing_id=3, motion="launch") == {"ok": True}
    assert bodies == [{"action": "act", "drawing_id": 3, "motion": "launch"}]
    reply = httpx.Response(409, json={"detail": "Seule une fusée peut décoller"})
    assert "fusée" in (await tool(None, drawing_id=1, motion="launch"))["error"]
    assert "error" in await tool(None, drawing_id=1, motion="explode")
    assert len(bodies) == 2
