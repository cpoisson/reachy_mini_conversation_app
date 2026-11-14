import logging

import httpx
from pydantic import ValidationError

from reachy_mini_conversation_app.livesketch import LiveSketchClient, bridge_client
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)

MOTIONS = ["launch", "land", "move", "stop", "turn", "jump", "spin", "dance"]


class LiveSketchAct(Tool):
    """Make one drawing on the LiveSketch screen perform an action."""

    name = "livesketch_act"
    description = (
        "Make a visible drawing act on the LiveSketch screen, using its ID from livesketch_get_scene. "
        "launch: a rocket waiting on its pad takes off (land brings it back early). "
        "move / stop / turn: start, stop or reverse a vehicle, boat, bird, character or cloud. "
        "jump, spin, dance: a short gesture any drawing can do. "
        "The scene's state field says whether a drawing is still, moving or flying."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "drawing_id": {"type": "integer", "minimum": 1},
            "motion": {"type": "string", "enum": MOTIONS},
        },
        "required": ["drawing_id", "motion"],
        "additionalProperties": False,
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: object) -> dict[str, object]:
        """Send the action; the screen refuses one that does not fit the drawing."""
        drawing_id, motion = kwargs.get("drawing_id"), kwargs.get("motion")
        if type(drawing_id) is not int or motion not in MOTIONS:
            return {"error": f"Expected drawing_id and a motion among {', '.join(MOTIONS)}"}
        try:
            async with bridge_client() as client:
                return await LiveSketchClient(client).command(
                    {"action": "act", "drawing_id": drawing_id, "motion": motion}
                )
        except httpx.HTTPStatusError as exc:
            logger.warning("LiveSketch action rejected: %s", exc)
            reason = (
                "the drawing left the table" if exc.response.status_code == 404 else "it does not fit this drawing"
            )
            try:
                detail = exc.response.json().get("detail")
            except ValueError:
                detail = None
            if isinstance(detail, str) and exc.response.status_code == 409:
                reason = detail
            return {"error": f"Action not played ({reason}); do not claim success"}
        except (httpx.HTTPError, ValidationError, ValueError) as exc:
            logger.warning("LiveSketch action failed: %s", exc)
            return {"error": "LiveSketch unavailable; do not claim success"}
