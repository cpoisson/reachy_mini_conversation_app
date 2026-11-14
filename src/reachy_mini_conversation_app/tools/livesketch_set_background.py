import logging

import httpx
from pydantic import ValidationError

from reachy_mini_conversation_app.livesketch import LiveSketchClient, bridge_client
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)

BACKGROUNDS = ["paper", "space", "moon", "countryside", "mountain", "sea", "city"]


class LiveSketchSetBackground(Tool):
    """Change the scenery behind the drawings on the LiveSketch screen."""

    name = "livesketch_set_background"
    description = (
        "Change the paper-cut scenery behind the drawings on the LiveSketch screen: "
        "paper (plain sheet), space (stars and a ringed planet), moon (lunar ground, Earth in the sky), "
        "countryside (green hills and trees), mountain (snowy peaks and pines), sea (waves and an island), "
        "city (buildings and a sidewalk). The current one is in the scene's background field."
    )
    parameters_schema = {
        "type": "object",
        "properties": {"background": {"type": "string", "enum": BACKGROUNDS}},
        "required": ["background"],
        "additionalProperties": False,
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: object) -> dict[str, object]:
        """Execute the LiveSketch tool without interrupting conversation on failure."""
        background = kwargs.get("background")
        if background not in BACKGROUNDS:
            return {"error": f"Expected a background among {', '.join(BACKGROUNDS)}"}
        try:
            async with bridge_client() as client:
                return await LiveSketchClient(client).command({"action": "set_background", "background": background})
        except (httpx.HTTPError, ValidationError, ValueError) as exc:
            logger.warning("LiveSketch tool failed: %s", exc)
            return {"error": "LiveSketch unavailable or command rejected; do not claim success"}
