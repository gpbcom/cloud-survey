from __future__ import annotations

# Standard Library Imports.
from typing import Dict, List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.drivers.collectors.metric_source_entry import MetricSourceEntry


class CollectorCatalog(BaseModel):
    """What the metric collectors read, and where (`conf/metrics/collectors.yaml`).

    Attributes:
        user_agent (str): The user agent of the requests (SEC EDGAR refuses the anonymous ones).
        sec_user_agent_env (str): The environment variable holding the SEC user agent with a contact, if set.
        github_token_env (str): The environment variable holding a GitHub token (60 requests an hour without it).
        peeringdb_key_env (str): The environment variable holding a PeeringDB API key (anonymous queries are throttled).
        capex_concepts (List[str]): The US-GAAP concepts of the capital expenditure, the preferred first.
        entries (List[MetricSourceEntry]): Where each provider is found.

    Notes:
        The secrets are never written in the file: only the names of the environment variables holding them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    user_agent: str = Field(min_length=1, description="The user agent of the requests.")
    sec_user_agent_env: str = Field(default="CRAWLER_SEC_USER_AGENT", description="The SEC user agent variable.")
    github_token_env: str = Field(default="GITHUB_TOKEN", description="The GitHub token variable.")
    peeringdb_key_env: str = Field(default="PEERINGDB_API_KEY", description="The PeeringDB API key variable.")
    capex_concepts: List[str] = Field(default_factory=list, description="The capital expenditure concepts.")
    entries: List[MetricSourceEntry] = Field(default_factory=list, description="Where each provider is found.")

    @field_validator("user_agent", "sec_user_agent_env", "github_token_env", "peeringdb_key_env", mode="before")
    def validate_text(cls, value: JsonValue) -> JsonValue:
        """Validate a raw text: trimmed.

        Args:
            value (JsonValue): The raw text.

        Returns:
            JsonValue: The text, trimmed.
        """
        return value.strip() if isinstance(value, str) else value

    @field_validator("capex_concepts", mode="before")
    def validate_concepts(cls, value: JsonValue) -> JsonValue:
        """Validate the raw concepts: trimmed, each once, in their order.

        Args:
            value (JsonValue): The raw concepts.

        Returns:
            JsonValue: The concepts.
        """
        if not isinstance(value, list):
            return value
        unique: List[JsonValue] = [*dict.fromkeys(str(item).strip() for item in value if str(item).strip())]
        return unique

    @field_validator("entries", mode="before")
    def validate_entries(cls, value: JsonValue) -> JsonValue:
        """Validate the raw entries: the last entry of a provider wins.

        Args:
            value (JsonValue): The raw entries.

        Returns:
            JsonValue: One entry per provider, in their order.
        """
        if not isinstance(value, list):
            return value
        by_provider: Dict[str, JsonValue] = {}
        for item in value:
            key = str(item.get("provider")) if isinstance(item, dict) else str(id(item))
            by_provider[key] = item
        unique: List[JsonValue] = list(by_provider.values())
        return unique
