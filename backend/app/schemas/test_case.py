"""Test case schema for Aegis Vuldris.

Defines the YAML/JSON structure for seeded security test case files,
including single-turn and multi-turn conversation definitions, grading
configuration, and expected safe behavior documentation.
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TestCaseCategory(StrEnum):
    PROMPT_INJECTION = "prompt_injection"
    JAILBREAK = "jailbreak"
    PRIVACY_LEAKAGE = "privacy_data_leakage"
    RAG_ATTACK = "rag_attack"
    AGENT_TOOL_USE = "agent_tool_use"


class GradingMethod(StrEnum):
    KEYWORD = "keyword"
    REGEX = "regex"
    JUDGE_MODEL = "judge_model"


class ConverterRef(BaseModel):
    """A reference to a text transform applied to the prompt before it is sent.

    Encoding an attack is what makes an obfuscation test reproducible, so the
    declared converters travel with the test case rather than being baked into
    the prompt text. That keeps the original instruction visible in the YAML and
    the applied transform auditable.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    params: dict[str, Any] = Field(default_factory=dict)


class TestCaseMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(min_length=1, max_length=1_000_000)


class JudgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Optional model override for the judge call. When omitted, the project's
    # judge target supplies the model; set it to pin a different model on the
    # same judge endpoint (case authors usually omit it — the operator picks
    # the judge model when configuring the target).
    model: str | None = Field(default=None, min_length=1, max_length=200)
    # Optional explicit judge target for this test. When omitted, the
    # project's judge_target_id supplies the judge.
    target_id: str | None = Field(default=None, min_length=1, max_length=64)
    prompt: str = Field(min_length=1, max_length=10_000)
    pass_indicator: str | None = Field(default=None, min_length=1, max_length=500)
    fail_indicator: str | None = Field(default=None, min_length=1, max_length=500)
    inconclusive_indicator: str | None = Field(default=None, min_length=1, max_length=500)


class GradingConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    method: GradingMethod = GradingMethod.KEYWORD
    patterns: list[str] = Field(default_factory=list, max_length=100)
    regex_patterns: list[str] = Field(default_factory=list, max_length=50)
    case_insensitive: bool = True
    min_matches: int = Field(default=1, ge=1, le=100)
    severity: str = Field(default="medium", min_length=1, max_length=20)
    title: str = Field(
        default="Potential security issue detected",
        min_length=1,
        max_length=200,
    )
    judge: JudgeConfig | None = None


class TestCaseTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[TestCaseMessage] = Field(min_length=1, max_length=100)


class TestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # ``attack_id`` and ``version`` are copied into a seeded test's config so
    # a later run can be compared with the exact attack definition that
    # produced it. Bundled legacy cases receive a deterministic ID from their
    # path in ``load_test_case``; new contributed cases should declare one.
    attack_id: str | None = Field(
        default=None,
        min_length=3,
        max_length=200,
        pattern=r"^[a-z0-9][a-z0-9._/-]*$",
    )
    version: str = Field(default="1.0.0", min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    category: TestCaseCategory
    provider: str = Field(min_length=1, max_length=100)
    required_capabilities: list[str] = Field(default_factory=list, max_length=50)
    system_prompt: str | None = Field(default=None, max_length=1_000_000)
    prompts: list[TestCaseMessage] = Field(default_factory=list, max_length=100)
    # Transforms applied to every prompt in this test, in order. Applied
    # by the execution engine, so the YAML keeps the plain instruction and
    # the encoding stays visible and reproducible.
    converters: list[ConverterRef] = Field(default_factory=list, max_length=10)
    turns: list[TestCaseTurn] = Field(default_factory=list, max_length=20)
    expected_safe_behavior: str = Field(min_length=1, max_length=2000)
    security_property: str | None = Field(default=None, max_length=2000)
    references: list[str] = Field(default_factory=list, max_length=20)
    known_limitations: list[str] = Field(default_factory=list, max_length=20)
    grading: GradingConfig = Field(default_factory=GradingConfig)
    max_retries: int = Field(default=0, ge=0, le=10)
    timeout_seconds: float = Field(default=30.0, ge=1.0, le=600.0)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=100_000)
    stop: list[str] | None = Field(default=None, max_length=50)
    tags: list[str] = Field(default_factory=list, max_length=50)

    def to_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {}
        if self.system_prompt is not None:
            config["system_prompt"] = self.system_prompt
        if self.prompts:
            config["prompts"] = [msg.model_dump() for msg in self.prompts]
        if self.turns:
            config["turns"] = [
                {"messages": [msg.model_dump() for msg in turn.messages]} for turn in self.turns
            ]
        config["grading"] = self.grading.model_dump()
        if self.attack_id is not None:
            config["attack"] = {
                "id": self.attack_id,
                "version": self.version,
                "category": self.category.value,
                "security_property": self.security_property or self.expected_safe_behavior,
                "references": self.references,
                "known_limitations": self.known_limitations,
            }
        config["max_retries"] = self.max_retries
        config["timeout_seconds"] = self.timeout_seconds
        if self.temperature is not None:
            config["temperature"] = self.temperature
        if self.max_tokens is not None:
            config["max_tokens"] = self.max_tokens
        if self.converters:
            config["converters"] = [ref.model_dump() for ref in self.converters]
        if self.stop is not None:
            config["stop"] = self.stop
        return config


__all__ = [
    "ConverterRef",
    "GradingConfig",
    "GradingMethod",
    "JudgeConfig",
    "TestCase",
    "TestCaseCategory",
    "TestCaseMessage",
    "TestCaseTurn",
]
