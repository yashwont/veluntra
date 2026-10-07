from app.tools.document_tools import DOCUMENT_TOOLS
from app.tools.google_tools import GOOGLE_TOOLS
from app.tools.memory_tools import MEMORY_TOOLS
from app.tools.note_tools import NOTE_TOOLS
from app.tools.registry import ToolRegistry
from app.tools.search_tools import SEARCH_TOOLS
from app.tools.task_tools import TASK_TOOLS


def default_registry() -> ToolRegistry:
    """The tools the assistant may use. Deliberately no delete or external-send
    tools yet: those would need explicit user confirmation (spec section 10)."""
    return ToolRegistry([*TASK_TOOLS, *NOTE_TOOLS, *DOCUMENT_TOOLS, *MEMORY_TOOLS, *SEARCH_TOOLS, *GOOGLE_TOOLS])
