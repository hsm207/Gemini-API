"""Detection of Gemini error cards in a StreamGenerate payload.

When Gemini abandons a partially generated answer it does not signal an error.
The HTTP status is 200, the headers are ordinary, and the stream terminates
normally. The failure is only visible inside the payload, where the server
marks the rejected generation with a boolean.

    [[[[None, [None, 0, "<text>"]]]]], None, None, None, None, True, ...

The five slots after the text block hold the flag: ``True`` on a rejected
generation, ``None`` on a successful one. This is checked before the text
matching because it needs no knowledge of what the message says, so it also
catches wordings that have never been observed.

Kept in its own module so callers need only a couple of lines to adopt it and
so upstream changes to the client do not collide with it.
"""
from typing import Any, List, Optional

# Slots between a text block and the boolean marking its rejection.
TEXT_BLOCK_FLAG_OFFSET = 5

# The text block is wrapped as [[[[None, [None, 0, str]]]]]. Descending through
# the single-element wrappers is the only thing that varies between payloads.
_TEXT_BLOCK_WRAPPER_DEPTH = 4

# Wordings observed on the wire. The flag above is the primary signal; this is
# a fallback for a payload that arrives without it.
KNOWN_ERROR_MESSAGES = (
    "I encountered an error doing what you asked. Could you try again?",
    "Sorry, something went wrong. Please try your request again.",
    "I'm having a hard time fulfilling your request. "
    "Can I help you with something else instead?",
    "I seem to be encountering an error. Can I try something else for you?",
)


def is_rejected(payload: Any) -> bool:
    """Whether the payload carries the server's rejection flag."""
    if not isinstance(payload, list):
        return False
    for index, node in enumerate(payload):
        if not _is_text_block(node):
            continue
        flag = index + TEXT_BLOCK_FLAG_OFFSET
        if flag < len(payload) and payload[flag] is True:
            return True
    return False


def matches_known_message(text: Optional[str]) -> bool:
    """Whether ``text`` is one of the observed error wordings."""
    if not text:
        return False
    normalized = text.strip().lower()
    return any(normalized == known.lower() for known in KNOWN_ERROR_MESSAGES)


def is_error_card(payload: Any, candidate_text: Optional[str] = None) -> bool:
    """Whether this payload is a failed generation rather than a real answer.

    Args:
        payload: the decoded StreamGenerate payload for one frame.
        candidate_text: the candidate's text, used only by the message fallback.
    """
    return is_rejected(payload) or matches_known_message(candidate_text)


def error_summary(payload: Any, candidate_text: Optional[str] = None) -> Optional[str]:
    """A short human-readable reason, or ``None`` when nothing is wrong."""
    if is_rejected(payload):
        return "server marked the text block as rejected"
    if matches_known_message(candidate_text):
        return "response matched a known error message"
    return None


def _is_text_block(node: Any) -> bool:
    """Whether ``node`` is the ``[[[[None, [None, 0, str]]]]]`` wrapper."""
    node = _unwrap(node)
    if not (isinstance(node, list) and len(node) == 2 and node[0] is None
            and isinstance(node[1], list) and len(node[1]) == 3):
        return False
    inner = node[1]
    return inner[0] is None and inner[1] == 0 and isinstance(inner[2], str)


def _unwrap(node: Any) -> Any:
    """Descend through the single-element list wrappers around a text block."""
    for _ in range(_TEXT_BLOCK_WRAPPER_DEPTH):
        if not (isinstance(node, list) and len(node) == 1
                and isinstance(node[0], list)):
            break
        node = node[0]
    return node