"""Detects Gemini backend "error card" responses in batchexecute streams.

When Gemini fails mid-answer it does NOT signal an error in the transport.
The HTTP response is 200, the headers are clean, and the stream terminates
normally. Instead the server REPLACES the partially-generated answer with a
short canned apology (three distinct wordings observed; the exact list lives
in ExplicitErrorMessageRule.KNOWN_ERROR_MESSAGES).

Two real messages captured so far:
  * "I encountered an error doing what you asked. Could you try again?"
  * "Sorry, something went wrong. Please try your request again."

A third, found in a later capture:
  * "I'm having a hard time fulfilling your request. Can I help you with
     something else instead?"

Three independent rules detect this, OR'd together:

  1. TextBlockFlagRule       - structural. The server sets a boolean next to
                               the text block when it rejects a generation.
                               Needs no wording knowledge, so it catches both
                               unseen messages and failures that arrive before
                               any answer text exists.
  2. PayloadCollapseRule     - structural. The candidate text was replaced
                               wholesale rather than appended to. Threshold-free:
                               it tests replacement, not size.
  3. ExplicitErrorMessageRule - literal. The known canned messages, kept as an
                               exact-match list to grow as new ones are seen.

Any rule firing means the response is an error card.
"""
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Sequence


@dataclass(frozen=True)
class DetectionResult:
  """Immutable outcome of stream validation."""

  has_error: bool
  diagnostic_message: Optional[str] = None

  @classmethod
  def healthy(cls) -> "DetectionResult":
    return cls(has_error=False, diagnostic_message=None)

  @classmethod
  def failure(cls, message: str) -> "DetectionResult":
    return cls(has_error=True, diagnostic_message=message)


@dataclass(frozen=True)
class CandidateSnapshot:
  """One candidate's text as it appeared in a single stream frame."""

  text: str
  rcid: str
  is_completed: bool
  # True when this payload carried the server-side rejection flag that sits a
  # fixed distance after the text block. See TextBlockFlagRule.
  is_text_block_rejected: bool = False


class BatchExecuteFrameReader:
  """Walks the length-prefixed anti-XSSI framing of a batchexecute stream.

  Frames cannot be located by regex: digits appear inside JSON payloads too.
  The only correct approach is to walk the declared lengths sequentially.
  """

  XSSI_PREFIX = ")]}'"

  def iter_frames(self, stream_content: str) -> List[list]:
    content = self._strip_xssi_prefix(stream_content)
    decoder = json.JSONDecoder()
    frames: List[list] = []
    cursor = 0

    while cursor < len(content):
      newline = content.find("\n", cursor)
      if newline == -1:
        break

      header = content[cursor:newline].strip()
      if not header.isdigit():
        cursor += 1
        continue

      declared_length = int(header)
      payload_start = newline + 1
      payload_end = payload_start + declared_length

      try:
        frame, _ = decoder.raw_decode(content[payload_start:payload_end])
      except ValueError:
        # Corrupt frame: skip its declared span and keep going.
        cursor = payload_end
        continue

      frames.append(frame)
      cursor = payload_end

    return frames

  def _strip_xssi_prefix(self, raw_stream: str) -> str:
    if not raw_stream.startswith(self.XSSI_PREFIX):
      return raw_stream
    newline_index = raw_stream.find("\n")
    if newline_index == -1:
      return raw_stream
    return raw_stream[newline_index + 1:].lstrip()


class CandidateSnapshotExtractor:
  """Extracts candidate text across streaming updates.

  Text is read from decoded JSON, never by regex. The wire format is
  double-encoded, so candidate text appears escaped ("rc_..." with
  backslashes); a regex written against unescaped quotes can never match.
  """

  # Slots between a text block and the boolean that marks its rejection.
  TEXT_BLOCK_FLAG_OFFSET = 5

  def extract_snapshots(self, stream_content: str) -> List[CandidateSnapshot]:
    snapshots: List[CandidateSnapshot] = []
    for payload in self._iter_payloads(stream_content):
      rejected = self._payload_is_rejected(payload)
      for candidate in self._iter_candidates(payload):
        text = self._read_text(candidate)
        if text is None:
          continue
        snapshots.append(
            CandidateSnapshot(
                text=text,
                rcid=candidate[0],
                is_completed=self._read_is_completed(candidate),
                is_text_block_rejected=rejected,
            )
        )
    return snapshots

  def _payload_is_rejected(self, payload: list) -> bool:
    """Whether the payload carries the server-side rejection flag.

    A text block is nested as [[[[None, [None, 0, "<text>"]]]]]. Five slots
    after the block, the server sets True to mark a rejected generation; on a
    successful generation those slots stay None.
    """
    if not isinstance(payload, list):
      return False
    for index, node in enumerate(payload):
      if self._is_text_block(node):
        flag_index = index + self.TEXT_BLOCK_FLAG_OFFSET
        if flag_index < len(payload) and payload[flag_index] is True:
          return True
    return False

  def _is_text_block(self, node: object) -> bool:
    """True for the exact [[[[None, [None, 0, str]]]]] wrapper."""
    node = self._unwrap(node, depth=4)
    if not (isinstance(node, list) and len(node) == 2 and node[0] is None
            and isinstance(node[1], list) and len(node[1]) == 3):
      return False
    inner = node[1]
    return inner[0] is None and inner[1] == 0 and isinstance(inner[2], str)

  def _unwrap(self, node: object, depth: int) -> object:
    """Descend through single-element list wrappers."""
    for _ in range(depth):
      if not (isinstance(node, list) and len(node) == 1 and isinstance(node[0], list)):
        break
      node = node[0]
    return node

  def _iter_payloads(self, stream_content: str) -> List[list]:
    payloads = []
    for frame in self._frame_reader.iter_frames(stream_content):
      # Each frame is ["wrb.fr", null, "<json string>", ...]; the inner string
      # is the actual StreamGenerate payload.
      if not frame or not isinstance(frame[0], list):
        continue
      row = frame[0]
      if len(row) > 2 and isinstance(row[2], str):
        try:
          decoded = json.loads(row[2])
        except ValueError:
          continue
        if isinstance(decoded, list):
          payloads.append(decoded)
    return payloads

  def _iter_candidates(self, payload: list) -> List[list]:
    if len(payload) <= 4 or not isinstance(payload[4], list):
      return []
    return [
        candidate
        for candidate in payload[4]
        if isinstance(candidate, list)
        and candidate
        and isinstance(candidate[0], str)
        and candidate[0].startswith("rc_")
    ]

  def _read_text(self, candidate: list) -> Optional[str]:
    if len(candidate) > 1 and isinstance(candidate[1], list) and candidate[1]:
      text = candidate[1][0]
      if isinstance(text, str):
        return text
    return None

  def _read_is_completed(self, candidate: list) -> bool:
    if len(candidate) > 8 and isinstance(candidate[8], list) and candidate[8]:
      return candidate[8][0] == 2
    return False

  @property
  def _frame_reader(self) -> BatchExecuteFrameReader:
    if not hasattr(self, "_reader"):
      self._reader = BatchExecuteFrameReader()
    return self._reader


class DetectionRule(ABC):
  """Abstract strategy for inspecting stream state (Open/Closed Principle)."""

  @abstractmethod
  def evaluate(
      self, snapshots: Sequence[CandidateSnapshot]
  ) -> Optional[DetectionResult]:
    """Returns a DetectionResult when this rule detects a defect, else None."""
    raise NotImplementedError


class TextBlockFlagRule(DetectionRule):
  """Detects the server-side rejection flag that accompanies an error card.

  This is the strongest of the three rules. It is purely structural: it reads
  a boolean the server sets when it rejects a generation, so it works for
  wordings nobody has catalogued and for failures that arrive before any
  answer text exists.

  Layout, as observed on every error in the corpus:

      [[[[None, [None, 0, "<text>"]]]]], None, None, None, None, True, ...

  The five slots after the text block carry the flag: True on a rejected
  generation, None on a successful one.
  """

  def evaluate(
      self, snapshots: Sequence[CandidateSnapshot]
  ) -> Optional[DetectionResult]:
    for snapshot in snapshots:
      if snapshot.is_text_block_rejected:
        return DetectionResult.failure(
            f"Server marked the text block as rejected "
            f"(rejection flag set). Response text: "
            f"'{self._preview(snapshot.text)}'"
        )
    return None

  def _preview(self, text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[:limit] + "..."


class ExplicitErrorMessageRule(DetectionRule):
  """Detects known canned backend failure copy by exact match.

  This list is the catalogue of real-world error messages observed in the
  wild. Add an entry when a new one is captured. Matched case-insensitively
  against the whole message so trailing punctuation variants still hit.
  """

  KNOWN_ERROR_MESSAGES = (
      "I encountered an error doing what you asked. Could you try again?",
      "Sorry, something went wrong. Please try your request again.",
      "I'm having a hard time fulfilling your request. "
      "Can I help you with something else instead?",
      "I seem to be encountering an error. Can I try something else for you?",
  )

  def evaluate(
      self, snapshots: Sequence[CandidateSnapshot]
  ) -> Optional[DetectionResult]:
    for snapshot in snapshots:
      normalized = snapshot.text.strip().lower()
      for known in self.KNOWN_ERROR_MESSAGES:
        if normalized == known.lower():
          return DetectionResult.failure(
              f"Backend emitted a known error message: '{snapshot.text}'"
          )
    return None


class PayloadCollapseRule(DetectionRule):
  """Detects candidate text being replaced rather than extended.

  A healthy stream only ever appends: each frame's text starts with the
  previous frame's text. Gemini's mid-answer failure breaks that invariant -
  the partial answer is discarded and a short apology takes its place.

  The test is threshold-free on purpose. Comparing sizes (peak >= N, current
  <= M) only catches errors that happen to be large; testing for *replacement*
  catches them at any size. It also cannot be fooled by markdown flicker,
  because flicker rewrites a trailing fragment and preserves the opening, so
  the new text still extends the old one.

  Note both real captures share at least one leading character with the answer
  they replaced (0 chars in one, 1 in the other), so requiring a zero-length
  shared prefix would miss a genuine error. The correct test is "the new text
  is not a prefix-extension of the old", with no size or overlap conditions.
  """

  def evaluate(
      self, snapshots: Sequence[CandidateSnapshot]
  ) -> Optional[DetectionResult]:
    for index in range(1, len(snapshots)):
      previous = snapshots[index - 1].text
      current = snapshots[index].text

      if len(current) >= len(previous):
        continue
      # A shrink that is still a prefix-extension is ordinary backtracking,
      # not a replacement. Anything else discarded the answer.
      if previous.startswith(current):
        continue

      return DetectionResult.failure(
          f"Candidate text was replaced, not extended: "
          f"{len(previous)} -> {len(current)} characters. "
          f"Replacement began with '{self._preview(current)}'"
      )
    return None

  def _preview(self, text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[:limit] + "..."


@dataclass(frozen=True)
class StreamAnomalyDetector:
  """Coordinates extraction and OR-combines every configured detection rule."""

  rules: Sequence[DetectionRule] = field(
      default_factory=lambda: [
          TextBlockFlagRule(),
          PayloadCollapseRule(),
          ExplicitErrorMessageRule(),
      ]
  )

  def detect(self, stream_content: str) -> DetectionResult:
    snapshots = CandidateSnapshotExtractor().extract_snapshots(stream_content)

    for rule in self.rules:
      result = rule.evaluate(snapshots)
      if result and result.has_error:
        return result

    return DetectionResult.healthy()

  def detect_all(self, stream_content: str) -> List[DetectionResult]:
    """Returns every firing rule's result, in declaration order.

    Useful for diagnostics: shows *which* rule fired rather than only that
    one did.
    """
    snapshots = CandidateSnapshotExtractor().extract_snapshots(stream_content)
    return [
        result
        for result in (rule.evaluate(snapshots) for rule in self.rules)
        if result and result.has_error
    ]
