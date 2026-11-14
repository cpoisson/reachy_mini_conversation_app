import logging

import httpx
from pydantic import ValidationError

from reachy_mini_conversation_app.livesketch import LiveSketchClient, bridge_client
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)


class LiveSketchStopStory(Tool):
    """Stop the story playing on the LiveSketch screen and show all drawings again."""

    name = "livesketch_stop_story"
    description = "Stop the story playing on the LiveSketch screen and show all drawings again."
    parameters_schema = {"type": "object", "properties": {}, "additionalProperties": False}

    async def __call__(self, deps: ToolDependencies, **kwargs: object) -> dict[str, object]:
        """Execute the LiveSketch tool without interrupting conversation on failure."""
        try:
            async with bridge_client() as client:
                return await LiveSketchClient(client).command({"action": "stop_story"})
        except (httpx.HTTPError, ValidationError, ValueError) as exc:
            logger.warning("LiveSketch tool failed: %s", exc)
            return {"error": "LiveSketch unavailable or command rejected; do not claim success"}
