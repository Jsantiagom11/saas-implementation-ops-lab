from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from saas_ops.config import RiskThresholds
from saas_ops.models import Customer, Risk, Stage
from saas_ops.service import score_risk

NOW = datetime(2026, 8, 25, 12, tzinfo=UTC)
DEFAULTS = RiskThresholds()


def customer(
    *,
    stage: Stage = Stage.DISCOVERY,
    age: timedelta = timedelta(0),
    target_delta: timedelta = timedelta(days=30),
) -> Customer:
    return Customer(
        id=1,
        version=0,
        name="Andes Telecom",
        owner="Jorge Santiago",
        target_go_live=NOW + target_delta,
        contract_value=48_000,
        stage=stage,
        risk=Risk.LOW,
        created_at=NOW - age,
        updated_at=NOW - age,
    )


@pytest.mark.parametrize(
    ("age", "expected_risk", "expected_code"),
    [
        (timedelta(hours=48) - timedelta(seconds=1), Risk.LOW, None),
        (timedelta(hours=48), Risk.MEDIUM, "stage_sla_warning"),
        (timedelta(hours=72) - timedelta(seconds=1), Risk.MEDIUM, "stage_sla_warning"),
        (timedelta(hours=72), Risk.HIGH, "stage_sla_breached"),
        (timedelta(hours=72) + timedelta(seconds=1), Risk.HIGH, "stage_sla_breached"),
    ],
)
def test_stage_sla_boundaries(
    age: timedelta, expected_risk: Risk, expected_code: str | None
) -> None:
    assessment = score_risk(customer(age=age), now=NOW, thresholds=DEFAULTS)

    assert assessment.risk == expected_risk
    assert [reason.code for reason in assessment.reasons] == (
        [] if expected_code is None else [expected_code]
    )


@pytest.mark.parametrize(
    ("target_delta", "expected_risk", "expected_code"),
    [
        (timedelta(hours=168, seconds=1), Risk.LOW, None),
        (timedelta(hours=168), Risk.MEDIUM, "target_go_live_approaching"),
        (timedelta(seconds=1), Risk.MEDIUM, "target_go_live_approaching"),
        (timedelta(0), Risk.HIGH, "target_go_live_overdue"),
        (-timedelta(seconds=1), Risk.HIGH, "target_go_live_overdue"),
    ],
)
def test_go_live_boundaries(
    target_delta: timedelta, expected_risk: Risk, expected_code: str | None
) -> None:
    assessment = score_risk(
        customer(target_delta=target_delta), now=NOW, thresholds=DEFAULTS
    )

    assert assessment.risk == expected_risk
    assert [reason.code for reason in assessment.reasons] == (
        [] if expected_code is None else [expected_code]
    )


def test_multiple_reasons_are_ordered_by_severity_then_code() -> None:
    assessment = score_risk(
        customer(age=timedelta(hours=48), target_delta=-timedelta(hours=1)),
        now=NOW,
        thresholds=DEFAULTS,
    )

    assert assessment.risk == Risk.HIGH
    assert [reason.code for reason in assessment.reasons] == [
        "target_go_live_overdue",
        "stage_sla_warning",
    ]


@pytest.mark.parametrize("stage", [Stage.GO_LIVE, Stage.HYPERCARE])
def test_post_go_live_ignores_target_but_not_stage_age(stage: Stage) -> None:
    assessment = score_risk(
        customer(stage=stage, age=timedelta(hours=72), target_delta=-timedelta(days=1)),
        now=NOW,
        thresholds=DEFAULTS,
    )

    assert assessment.risk == Risk.HIGH
    assert [reason.code for reason in assessment.reasons] == ["stage_sla_breached"]


def test_complete_customer_is_always_low() -> None:
    assessment = score_risk(
        customer(
            stage=Stage.COMPLETE,
            age=timedelta(days=365),
            target_delta=-timedelta(days=365),
        ),
        now=NOW,
        thresholds=DEFAULTS,
    )

    assert assessment.risk == Risk.LOW
    assert assessment.reasons == []


def test_equivalent_offsets_produce_identical_assessments() -> None:
    local_offset = timezone(timedelta(hours=-5))
    assessment_utc = score_risk(customer(), now=NOW, thresholds=DEFAULTS)
    assessment_offset = score_risk(
        customer().model_copy(
            update={
                "target_go_live": customer().target_go_live.astimezone(local_offset),
                "updated_at": customer().updated_at.astimezone(local_offset),
            }
        ),
        now=NOW.astimezone(local_offset),
        thresholds=DEFAULTS,
    )

    assert assessment_offset == assessment_utc


def test_naive_input_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone offset"):
        customer().model_copy(update={"target_go_live": NOW.replace(tzinfo=None)}).model_validate(
            customer().model_dump() | {"target_go_live": NOW.replace(tzinfo=None)}
        )


def test_naive_clock_is_rejected() -> None:
    with pytest.raises(ValueError, match="now must include a timezone offset"):
        score_risk(customer(), now=NOW.replace(tzinfo=None), thresholds=DEFAULTS)


def test_custom_thresholds_move_boundaries() -> None:
    thresholds = RiskThresholds(
        stage_warning_hours=24,
        stage_breach_hours=36,
        go_live_warning_hours=48,
    )

    assert score_risk(
        customer(age=timedelta(hours=24)), now=NOW, thresholds=thresholds
    ).risk == Risk.MEDIUM
    assert score_risk(
        customer(age=timedelta(hours=36)), now=NOW, thresholds=thresholds
    ).risk == Risk.HIGH


@pytest.mark.parametrize(
    "kwargs",
    [
        {"stage_warning_hours": -1},
        {"stage_warning_hours": 72, "stage_breach_hours": 48},
        {"stage_warning_hours": 72, "stage_breach_hours": 72},
        {"go_live_warning_hours": -1},
    ],
)
def test_invalid_threshold_relationships_fail(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        RiskThresholds(**kwargs)


def test_invalid_environment_integer_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAAS_OPS_STAGE_WARNING_HOURS", "abc")

    with pytest.raises(ValueError, match="must be an integer"):
        RiskThresholds.from_env()


def test_future_stage_timestamp_surfaces_data_quality_risk() -> None:
    assessment = score_risk(
        customer(age=-timedelta(hours=1)), now=NOW, thresholds=DEFAULTS
    )

    assert assessment.risk == Risk.HIGH
    assert [reason.code for reason in assessment.reasons] == ["stage_timestamp_in_future"]
