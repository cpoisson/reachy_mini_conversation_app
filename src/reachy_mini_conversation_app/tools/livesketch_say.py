import logging

import httpx
from pydantic import ValidationError

from reachy_mini_conversation_app.livesketch import LiveSketchClient, bridge_client
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)


class LiveSketchSay(Tool):
    """Display a short speech bubble on a visible drawing, using its ID from livesketch_get_scene."""

    name = "livesketch_say"
    description = "Display a short speech bubble on a visible drawing, using its ID from livesketch_get_scene."
    parameters_schema = {
        "type": "object",
        "properties": {
            "drawing_id": {"type": "integer", "minimum": 1},
            "text": {"type": "string", "minLength": 1, "maxLength": 200},
        },
        "required": ["drawing_id", "text"],
        "additionalProperties": False,
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: object) -> dict[str, object]:
        """Execute the LiveSketch tool without interrupting conversation on failure."""
        try:
            async with bridge_client() as client:
                bridge = LiveSketchClient(client)
                drawing_id, text = kwargs.get("drawing_id"), kwargs.get("text")
                if type(drawing_id) is not int or not isinstance(text, str) or not text.strip() or len(text) > 200:
                    return {"error": "Expected drawing_id and 1–200 characters of text"}
                return await bridge.command({"action": "say", "drawing_id": drawing_id, "text": text})
        except (httpx.HTTPError, ValidationError, ValueError) as exc:
            logger.warning("LiveSketch tool failed: %s", exc)
            return {"error": "LiveSketch unavailable or command rejected; do not claim success"}
