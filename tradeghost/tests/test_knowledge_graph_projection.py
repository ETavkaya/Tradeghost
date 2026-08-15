from tradeghost.services.knowledge_graph.projection import build_report_projection


def test_build_report_projection_preserves_only_deterministic_report_facts() -> None:
    projection = build_report_projection(
        {
            "id": "11111111-1111-4111-8111-111111111111",
            "cohort_id": "22222222-2222-4222-8222-222222222222",
            "cohort_name": "Momentum cohort",
            "market": "us",
            "report_date": "2026-08-15",
            "report_mode": "followup",
            "created_at": "2026-08-15T12:00:00+00:00",
            "report_markdown": "Deterministic report body",
            "candidate_followup_json": [
                {
                    "symbol": "TSLA",
                    "company_name": "Tesla, Inc.",
                    "selected_categories": ["trend_mode", "momentum_mode"],
                    "selected_setup_type": "pullback",
                    "validity_state": "valid",
                }
            ],
        }
    )

    assert projection.report["report_id"] == "11111111-1111-4111-8111-111111111111"
    assert projection.report["market"] == "us"
    assert projection.segment["text"] == "Deterministic report body"
    assert projection.assets == [
        {
            "asset_key": "us:TSLA",
            "symbol": "TSLA",
            "market": "us",
            "asset_type": "equity",
            "company_name": "Tesla, Inc.",
        }
    ]
    assert {(row["signal_type"], row["state"]) for row in projection.signals} == {
        ("selection_category", "trend_mode"),
        ("selection_category", "momentum_mode"),
        ("setup_type", "pullback"),
        ("candidate_validity", "valid"),
    }
    assert all("target_price" not in row for row in projection.signals)
