import logging

import httpx
from pydantic import ValidationError

from reachy_mini_conversation_app.livesketch import LiveSketchClient, bridge_client
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)


class LiveSketchGetScene(Tool):
    """Read the currently visible drawings on the LiveSketch table; call before describing or selecting drawings."""

    name = "livesketch_get_scene"
    description = (
        "Read the currently visible drawings on the LiveSketch table; call before describing or selecting drawings."
    )
    parameters_schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def __call__(self, deps: ToolDependencies, **kwargs: object) -> dict[str, object]:
        """Execute the LiveSketch tool without interrupting conversation on failure."""
        try:
            async with bridge_client() as client:
                bridge = LiveSketchClient(client)
                scene = await bridge.scene()
                return scene.model_dump()
        except (httpx.HTTPError, ValidationError, ValueError) as exc:
            logger.warning("LiveSketch tool failed: %s", exc)
            return {"error": "LiveSketch unavailable or command rejected; do not claim success"}
