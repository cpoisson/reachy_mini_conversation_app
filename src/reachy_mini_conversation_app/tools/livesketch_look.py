import logging

import httpx
from pydantic import ValidationError

from reachy_mini_conversation_app.livesketch import LiveSketchClient, bridge_client
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)


class LiveSketchLook(Tool):
    """Look at the physical drawing table through its overhead camera."""

    name = "livesketch_look"
    description = (
        "Capture a fresh image of the LiveSketch drawing table from its overhead camera. "
        "Use to look at the table, describe drawings, colors or visual details, or answer what you see. "
        "This shows the physical table, not the robot's own camera or the animated screen. "
        "Orange numbered badges mark each detected drawing with its livesketch_get_scene ID."
    )
    parameters_schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def __call__(self, deps: ToolDependencies, **kwargs: object) -> dict[str, object]:
        """Return a JPEG for the conversation backend's existing image input path."""
        try:
            async with bridge_client() as client:
                image = await LiveSketchClient(client).image()
                return image.model_dump()
        except (httpx.HTTPError, ValidationError, ValueError) as exc:
            logger.warning("LiveSketch table capture failed: %s", exc)
            return {"error": "Table image unavailable; do not invent a visual description"}
