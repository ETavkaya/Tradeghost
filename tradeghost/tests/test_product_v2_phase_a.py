from tradeghost.shared.config.settings import Settings


def test_product_v2_features_are_disabled_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.product_v2_enabled is False
    assert settings.market_state_enabled is False
    assert settings.strategy_lab_enabled is False
    assert settings.operational_reporting_enabled is False
    assert settings.trading212_read_only_enabled is False


def test_product_v2_flags_do_not_disable_existing_followup_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.daily_cohort_followup_enabled is True
    assert settings.daily_cohort_followup_schedule == "23:30"
    assert settings.daily_cohort_followup_timezone == "Europe/London"
