"""Pure schema-v1 analytics validation. No collection, I/O, or persistence.

Breaking shape or semantic changes require a new schema version and an explicit
reader/migration policy; never silently reinterpret existing version-1 events.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, TypeAdapter,
    UUID4, field_validator, model_validator,
)

SCHEMA_VERSION = 1
MAX_EVENT_BYTES = 4096
MAX_COUNTER = 2**31 - 1


def _uuid(value):
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value
    ):
        raise ValueError("expected a canonical UUID")
    return UUID(value)


def _utc_timestamp(value):
    if isinstance(value, str):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}(?:Z|\+00:00)", value):
            raise ValueError("expected UTC RFC3339 with three fractional digits")
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
        raise ValueError("expected a timezone-aware UTC datetime")
    if value.microsecond % 1000:
        raise ValueError("timestamp precision must be whole milliseconds")
    return value.astimezone(timezone.utc)


EventUUID = Annotated[UUID4, BeforeValidator(_uuid)]
UTCTimestamp = Annotated[
    datetime, BeforeValidator(_utc_timestamp),
    PlainSerializer(lambda value: value.isoformat(timespec="milliseconds").replace("+00:00", "Z"), return_type=str, when_used="json"),
]
PositiveCounter = Annotated[int, Field(strict=True, ge=1, le=MAX_COUNTER)]
Latency = Annotated[int, Field(strict=True, ge=0, le=300000)]
MysteryID = Annotated[str, Field(min_length=6, max_length=11, pattern=r"^ms-[0-9]{3,8}$")]
Revision = Annotated[str, Field(
    min_length=1, max_length=64,
    pattern=r"^(?:[0-9a-f]{7,40}|v?[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}(?:-[a-z0-9]+(?:[.-][a-z0-9]+)*)?)$",
)]
Mode = Literal["offline", "ai"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, revalidate_instances="always", hide_input_in_errors=True)


class StartedProperties(StrictModel):
    start_source: Literal["page_load", "start_button", "random_button", "api", "unknown"] | None = None


class AttemptProperties(StrictModel):
    attempt_id: EventUUID


class AnsweredProperties(AttemptProperties):
    response_category: Literal["yes", "no", "irrelevant", "unknown", "ask_yes_no", "almost_solved", "solved"]
    response_origin: Literal["offline_stub", "ai_tool", "ai_fallback"]
    latency_ms: Latency | None = None


class HintRequestedProperties(AttemptProperties):
    pre_terminal: bool


class HintDeliveredProperties(HintRequestedProperties):
    hint_number: PositiveCounter
    latency_ms: Latency | None = None


class SolvedProperties(AttemptProperties):
    solve_method: Literal["required_facts", "moderator_label"]


class RevealedProperties(AttemptProperties):
    establishes_outcome: bool


class AbandonedProperties(StrictModel):
    last_activity_at: UTCTimestamp
    inactivity_seconds: Literal[1800]
    rule_version: Literal["inactivity_v1"]

    @field_validator("inactivity_seconds", mode="before")
    @classmethod
    def integer_seconds(cls, value):
        if type(value) is not int:
            raise ValueError("inactivity_seconds must be an integer")
        return value


class ErrorProperties(AttemptProperties):
    operation: Literal["create", "message", "hint", "reveal", "join"]
    error_code: Literal["invalid_request", "unknown_room", "unknown_mystery", "ai_timeout", "ai_failure", "invalid_ai_output", "internal"]
    stage: Literal["before_acceptance", "processing"]
    http_status: Annotated[int, Field(strict=True, ge=400, le=599)] | None = None
    latency_ms: Latency | None = None


class EventEnvelope(StrictModel):
    schema_version: Literal[1]
    event_id: EventUUID
    environment: Literal["production", "staging", "local", "test"]
    occurred_at: UTCTimestamp
    recorded_at: UTCTimestamp
    game_session_id: EventUUID | None
    mystery_id: MysteryID | None
    browser_visit_id: EventUUID | None
    mode: Mode | None
    game_sequence: PositiveCounter | None
    content_revision: Revision | None = None
    app_revision: Revision | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        # Literal[1] alone also accepts True and 1.0 in Pydantic.
        if type(value) is not int:
            raise ValueError("schema_version must be an integer")
        return value

    @model_validator(mode="after")
    def validate_envelope(self):
        if self.recorded_at < self.occurred_at:
            raise ValueError("recorded_at must not precede occurred_at")
        if (self.game_session_id is None) != (self.game_sequence is None):
            raise ValueError("game association and sequence must be present together")
        if self.game_session_id is not None and self.mystery_id is None:
            raise ValueError("an associated game requires a mystery ID")
        if self.mode is None and self.properties.stage != "before_acceptance":
            raise ValueError("only an error before acceptance may have an unknown mode")
        if len(self.model_dump_json().encode("utf-8")) > MAX_EVENT_BYTES:
            raise ValueError("event exceeds 4 KiB")
        return self


class GameEvent(EventEnvelope):
    source: Literal["server"]
    game_session_id: EventUUID
    mystery_id: MysteryID
    mode: Mode
    game_sequence: PositiveCounter


class GameStarted(GameEvent):
    event_name: Literal["game_started"]
    properties: StartedProperties


class QuestionSubmitted(GameEvent):
    event_name: Literal["question_submitted"]
    properties: AttemptProperties


class QuestionAnswered(GameEvent):
    event_name: Literal["question_answered"]
    properties: AnsweredProperties

    @model_validator(mode="after")
    def validate_response_mode(self):
        p = self.properties
        if self.mode == "offline":
            if p.response_origin != "offline_stub" or p.response_category != "unknown":
                raise ValueError("offline responses must be unknown offline stubs")
        elif p.response_origin == "offline_stub":
            raise ValueError("AI responses cannot be offline stubs")
        if p.response_origin == "ai_fallback" and p.response_category != "unknown":
            raise ValueError("AI fallback must be unknown")
        return self


class HintRequested(GameEvent):
    event_name: Literal["hint_requested"]
    properties: HintRequestedProperties


class HintDelivered(GameEvent):
    event_name: Literal["hint_delivered"]
    properties: HintDeliveredProperties


class GameSolved(GameEvent):
    event_name: Literal["game_solved"]
    properties: SolvedProperties


class SolutionRevealed(GameEvent):
    event_name: Literal["solution_revealed"]
    properties: RevealedProperties


class GameAbandoned(GameEvent):
    event_name: Literal["game_abandoned"]
    source: Literal["derived"]
    properties: AbandonedProperties

    @model_validator(mode="after")
    def validate_inactivity_time(self):
        # Subtract instead of adding to avoid overflow at datetime.max.
        if self.occurred_at - self.properties.last_activity_at != timedelta(seconds=1800):
            raise ValueError("abandonment must occur 1800 seconds after last activity")
        return self


class GameError(EventEnvelope):
    event_name: Literal["game_error"]
    source: Literal["server"]
    properties: ErrorProperties


AnalyticsEvent = Annotated[
    GameStarted | QuestionSubmitted | QuestionAnswered | HintRequested | HintDelivered
    | GameSolved | SolutionRevealed | GameAbandoned | GameError,
    Field(discriminator="event_name"),
]
_EVENT_ADAPTER = TypeAdapter(AnalyticsEvent, config=ConfigDict(hide_input_in_errors=True))


def validate_event(value: dict | str | bytes) -> AnalyticsEvent:
    """Validate a dict or JSON without side effects; never log invalid payloads.

    Pydantic ValidationError is a ValueError. Oversized JSON is rejected before
    parsing with ValueError. Consumers must not log structured errors with input
    values or diagnostics: keys/tags/context may also contain untrusted content.
    Map failures to bounded operational codes instead.
    """
    if isinstance(value, (str, bytes)):
        if len(value.encode("utf-8") if isinstance(value, str) else value) > MAX_EVENT_BYTES:
            raise ValueError("event exceeds 4 KiB")
        return _EVENT_ADAPTER.validate_json(value)
    return _EVENT_ADAPTER.validate_python(value)
