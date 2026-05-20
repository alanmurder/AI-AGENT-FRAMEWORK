"""L1 Memory evolution — extract preferences and facts from conversations using LLM."""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

EXTRACTION_SYSTEM_PROMPT = """You are a memory extraction assistant. Given a conversation summary, extract:

1. **User Preferences** — things the user explicitly or implicitly prefers, likes, or dislikes.
2. **Key Facts** — important factual information about the user, their work, or their context that should be remembered for future interactions.

Rules:
- Only extract information that is clearly stated or strongly implied
- Do NOT extract the assistant's responses or actions
- Do NOT extract vague or ambiguous statements
- Format each item as a concise bullet point
- If no preferences or facts are found, output "None" for that section

Output format (must be exactly this):
## Preferences
- item1
- item2
(or "None")

## Facts
- item1
- item2
(or "None")"""

EXTRACTION_USER_PROMPT = """Here is the conversation summary to analyze:

{summary}

Extract user preferences and key facts from this conversation."""


class MemoryEvolution:
    """L1 memory evolution: uses a lightweight LLM to extract preferences and facts from conversations."""

    def __init__(self, model: BaseChatModel):
        self.model = model

    def extract(self, conversation_summary: str) -> dict[str, list[str]]:
        """Extract preferences and facts from a conversation summary.

        Returns {"preferences": [...], "facts": [...]}.
        """
        if not conversation_summary.strip():
            return {"preferences": [], "facts": []}

        messages = [
            SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=EXTRACTION_USER_PROMPT.format(summary=conversation_summary)),
        ]

        response = self.model.invoke(messages)
        content = response.content

        preferences, facts = self._parse_response(content)
        return {"preferences": preferences, "facts": facts}

    def _parse_response(self, content: str) -> tuple[list[str], list[str]]:
        """Parse the LLM response into preferences and facts lists."""
        preferences = []
        facts = []

        sections = content.split("##")
        for section in sections:
            lines = section.strip().split("\n")
            header = lines[0].strip().lower() if lines else ""

            if "preference" in header:
                for line in lines[1:]:
                    item = line.strip().lstrip("- ").strip()
                    if item and item.lower() != "none":
                        preferences.append(item)

            elif "fact" in header:
                for line in lines[1:]:
                    item = line.strip().lstrip("- ").strip()
                    if item and item.lower() != "none":
                        facts.append(item)

        return preferences, facts