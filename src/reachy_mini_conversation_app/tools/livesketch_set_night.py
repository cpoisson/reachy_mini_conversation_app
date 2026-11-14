import logging

import httpx
from pydantic import ValidationError

from reachy_mini_conversation_app.livesketch import LiveSketchClient, bridge_client
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)


class LiveSketchSetNight(Tool):
    """Set night (true) or day (false) on the LiveSketch screen."""

    name = "livesketch_set_night"
    description = "Set night (true) or day (false) on the LiveSketch screen."
    parameters_schema = {
        "type": "object",
        "properties": {"enabled": {"type": "boolean"}},
        "required": ["enabled"],
        "additionalProperties": False,
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: object) -> dict[str, object]:
        """Execute the LiveSketch tool without interrupting conversation on failure."""
        try:
            async with bridge_client() as client:
                bridge = LiveSketchClient(client)
                enabled = kwargs.get("enabled")
                if not isinstance(enabled, bool):
                    return {"error": "Expected enabled: true or false"}
                return await bridge.command({"action": "set_night", "enabled": enabled})
        except (httpx.HTTPError, ValidationError, ValueError) as exc:
            logger.warning("LiveSketch tool failed: %s", exc)
            return {"error": "LiveSketch unavailable or command rejected; do not claim success"}
