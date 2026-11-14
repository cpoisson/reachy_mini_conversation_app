import logging

import httpx
from pydantic import ValidationError

from reachy_mini_conversation_app.livesketch import LiveSketchClient, bridge_client
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.tools.livesketch_act import MOTIONS
from reachy_mini_conversation_app.tools.livesketch_set_background import BACKGROUNDS


logger = logging.getLogger(__name__)

NARRATE = (
    "The screen is now playing the story. Tell it aloud right away, in French, exactly in the script's order: "
    "the title, then for each scene its narration followed by its lines. Say each line with a voice for that "
    "character, without adding words, so your voice stays in time with the speech bubbles."
)


class LiveSketchTellStory(Tool):
    """Stage a short story on the LiveSketch screen with the drawings as characters."""

    name = "livesketch_tell_story"
    description = (
        "Play a short story on the LiveSketch screen. The drawings fade out, then each one appears when it "
        "first takes part and its lines show in a speech bubble; narration and title show as captions. "
        "A line may carry a motion (a rocket launch, a jump…), with or without text. "
        "Use drawing IDs from livesketch_get_scene. After success, narrate the same script aloud."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "maxLength": 80},
            "scenes": {
                "type": "array",
                "minItems": 1,
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "properties": {
                        "narration": {
                            "type": "string",
                            "maxLength": 400,
                            "description": "What the narrator says in this scene, one or two short sentences.",
                        },
                        "background": {
                            "type": "string",
                            "enum": BACKGROUNDS,
                            "description": "Optional scenery that fades in when this scene starts.",
                        },
                        "characters": {
                            "type": "array",
                            "maxItems": 8,
                            "items": {"type": "integer", "minimum": 1},
                            "description": "Drawings that appear in this scene without necessarily speaking.",
                        },
                        "lines": {
                            "type": "array",
                            "maxItems": 8,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "drawing_id": {"type": "integer", "minimum": 1},
                                    "text": {"type": "string", "minLength": 1, "maxLength": 160},
                                    "motion": {
                                        "type": "string",
                                        "enum": MOTIONS,
                                        "description": "Optional action played when this line starts.",
                                    },
                                },
                                "required": ["drawing_id"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "additionalProperties": False,
                },
            },
        },
        "required": ["scenes"],
        "additionalProperties": False,
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: object) -> dict[str, object]:
        """Send the whole script; the browser paces it at the estimated speaking rate."""
        scenes = kwargs.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            return {"error": "Expected at least one scene"}
        story: dict[str, object] = {"scenes": scenes}
        if isinstance(kwargs.get("title"), str) and kwargs["title"]:
            story["title"] = kwargs["title"]
        try:
            async with bridge_client() as client:
                result = await LiveSketchClient(client).command({"action": "story", "story": story})
        except httpx.HTTPStatusError as exc:
            logger.warning("LiveSketch story rejected: %s", exc)
            detail = "a drawing left the table" if exc.response.status_code == 404 else "invalid or rejected script"
            return {"error": f"Story not shown ({detail}); call livesketch_get_scene and do not claim success"}
        except (httpx.HTTPError, ValidationError, ValueError) as exc:
            logger.warning("LiveSketch story failed: %s", exc)
            return {"error": "LiveSketch unavailable; do not claim the story is on screen"}
        return {**result, "next": NARRATE}
