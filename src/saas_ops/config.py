import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RiskThresholds:
    stage_warning_hours: int = 48
    stage_breach_hours: int = 72
    go_live_warning_hours: int = 168

    def __post_init__(self) -> None:
        if self.stage_warning_hours < 0:
            raise ValueError("SAAS_OPS_STAGE_WARNING_HOURS must be >= 0")
        if self.stage_breach_hours <= self.stage_warning_hours:
            raise ValueError(
                "SAAS_OPS_STAGE_BREACH_HOURS must be greater than "
                "SAAS_OPS_STAGE_WARNING_HOURS"
            )
        if self.go_live_warning_hours < 0:
            raise ValueError("SAAS_OPS_GO_LIVE_WARNING_HOURS must be >= 0")

    @classmethod
    def from_env(cls) -> "RiskThresholds":
        return cls(
            stage_warning_hours=_environment_integer("SAAS_OPS_STAGE_WARNING_HOURS", 48),
            stage_breach_hours=_environment_integer("SAAS_OPS_STAGE_BREACH_HOURS", 72),
            go_live_warning_hours=_environment_integer("SAAS_OPS_GO_LIVE_WARNING_HOURS", 168),
        )


def _environment_integer(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw_value!r}") from exc
