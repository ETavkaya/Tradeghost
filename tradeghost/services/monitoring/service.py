from __future__ import annotations

import json
import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pandas as pd

from tradeghost.services.analysis_engine import AnalysisEngine
from tradeghost.services.scanner.engine import ScannerEngine
from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.market import normalize_symbol
from tradeghost.shared.models.schemas import (
    AlertProfileApplyRequest,
    AlertProfileSuggestRequest,
    AlertProfileSuggestionResponse,
    AlertProfileSuggestionRule,
    AlertEvent,
    AlertSignalType,
    AlertEventStatus,
    AlertEventStatusUpdateRequest,
    AlertRule,
    AlertRuleCreateRequest,
    AlertRuleType,
    AlertRuleUpdateRequest,
    MonitoringRunRequest,
    MonitoringRunSummary,
    MonitoringSchedule,
    MonitoringScheduleCreateRequest,
    MonitoringScheduleUpdateRequest,
    ScannerRequest,
    ScannerCategory,
    Watchlist,
    WatchlistCreateRequest,
    WatchlistItem,
    WatchlistItemCreateRequest,
    WatchlistRenameRequest,
)


class MonitoringService:
    _US_EXCHANGE_FALLBACK: dict[str, str] = {
        "NVDA": "NASDAQ",
        "AMD": "NASDAQ",
        "AAPL": "NASDAQ",
        "ORCL": "NYSE",
        "KO": "NYSE",
        "GS": "NYSE",
    }

    def __init__(self, analysis_engine: AnalysisEngine | None = None, scanner_engine: ScannerEngine | None = None) -> None:
        settings = get_settings()
        self.base_dir = settings.logs_dir / "monitoring"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.watchlists_path = self.base_dir / "watchlists.json"
        self.rules_path = self.base_dir / "alert_rules.json"
        self.events_path = self.base_dir / "alert_events.json"
        self.schedules_path = self.base_dir / "monitoring_schedules.json"
        self.analysis_engine = analysis_engine or AnalysisEngine()
        self.scanner_engine = scanner_engine or ScannerEngine(analysis_engine=self.analysis_engine)
        self._run_lock = threading.Lock()
        self._logger = logging.getLogger(__name__)

    def _write_json(self, path: Path, payload: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def _read_watchlists(self) -> list[Watchlist]:
        if not self.watchlists_path.exists():
            return []
        rows = json.loads(self.watchlists_path.read_text(encoding="utf-8"))
        return [Watchlist.model_validate(row) for row in rows]

    def _save_watchlists(self, rows: list[Watchlist]) -> None:
        self._write_json(self.watchlists_path, [row.model_dump(mode="json") for row in rows])

    def _read_rules(self) -> list[AlertRule]:
        if not self.rules_path.exists():
            return []
        rows = json.loads(self.rules_path.read_text(encoding="utf-8"))
        return [AlertRule.model_validate(row) for row in rows]

    def _save_rules(self, rows: list[AlertRule]) -> None:
        self._write_json(self.rules_path, [row.model_dump(mode="json") for row in rows])

    def _read_events(self) -> list[AlertEvent]:
        if not self.events_path.exists():
            return []
        rows = json.loads(self.events_path.read_text(encoding="utf-8"))
        return [AlertEvent.model_validate(row) for row in rows]

    def _save_events(self, rows: list[AlertEvent]) -> None:
        self._write_json(self.events_path, [row.model_dump(mode="json") for row in rows])

    def _read_schedules(self) -> list[MonitoringSchedule]:
        if not self.schedules_path.exists():
            return []
        rows = json.loads(self.schedules_path.read_text(encoding="utf-8"))
        return [MonitoringSchedule.model_validate(row) for row in rows]

    def _save_schedules(self, rows: list[MonitoringSchedule]) -> None:
        self._write_json(self.schedules_path, [row.model_dump(mode="json") for row in rows])

    @staticmethod
    def _normalize_interval(interval: str | None) -> str:
        value = (interval or "5m").strip().lower()
        if value in {"1m", "5m", "hourly", "daily"}:
            return value
        if value == "manual":
            return "manual"
        return "5m"

    @classmethod
    def _next_run_time(cls, interval: str, now: datetime) -> datetime | None:
        normalized = cls._normalize_interval(interval)
        if normalized == "manual":
            return None
        if normalized == "1m":
            return now + timedelta(minutes=1)
        if normalized == "5m":
            return now + timedelta(minutes=5)
        if normalized == "hourly":
            return now + timedelta(hours=1)
        return now + timedelta(days=1)

    def _ensure_default_schedule(self) -> None:
        rows = self._read_schedules()
        if rows:
            return
        now = datetime.now(UTC)
        default_schedule = MonitoringSchedule(
            id=str(uuid4()),
            name="Default Auto Polling",
            market="us",
            frequency="5m",
            watchlist_id=None,
            symbols=[],
            category="trend_mode",
            duration="1y",
            max_results=50,
            is_enabled=True,
            mode="auto",
            interval="5m",
            created_at=now,
            updated_at=now,
            last_run_at=None,
            next_run_at=self._next_run_time("5m", now),
        )
        self._save_schedules([default_schedule])

    def _build_symbol_targets(self, req: MonitoringRunRequest) -> list[tuple[str, object]]:
        watchlists = self._read_watchlists()
        scoped_watchlists = watchlists
        if req.watchlist_id:
            scoped_watchlists = [row for row in watchlists if row.id == req.watchlist_id]

        requested = {sym.strip().upper() for sym in req.symbols if sym.strip()}
        targets: list[tuple[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for watchlist in scoped_watchlists:
            for item in watchlist.items:
                if req.market is not None and item.market != req.market:
                    continue
                symbol_upper = item.symbol.upper()
                if requested and symbol_upper not in requested:
                    continue
                key = (symbol_upper, item.market.value)
                if key in seen:
                    continue
                seen.add(key)
                targets.append((symbol_upper, item.market))

        if requested and req.market is not None:
            for symbol_upper in sorted(requested):
                key = (symbol_upper, req.market.value)
                if key in seen:
                    continue
                seen.add(key)
                targets.append((symbol_upper, req.market))

        return targets[: req.max_symbols_per_batch]

    @classmethod
    def _resolve_exchange(cls, symbol: str, market: str, exchange: str | None = None) -> str:
        if market == "bist":
            return "BIST"
        if exchange and exchange.strip():
            return exchange.strip().upper()
        return cls._US_EXCHANGE_FALLBACK.get(symbol.upper(), "NASDAQ")

    # Watchlists
    def list_watchlists(self) -> list[Watchlist]:
        return self._read_watchlists()

    def create_watchlist(self, req: WatchlistCreateRequest) -> Watchlist:
        rows = self._read_watchlists()
        now = datetime.now(UTC)
        row = Watchlist(id=str(uuid4()), name=req.name.strip() or "Untitled Watchlist", created_at=now, updated_at=now, items=[])
        rows.append(row)
        self._save_watchlists(rows)
        return row

    def rename_watchlist(self, watchlist_id: str, req: WatchlistRenameRequest) -> Watchlist:
        rows = self._read_watchlists()
        for idx, row in enumerate(rows):
            if row.id != watchlist_id:
                continue
            rows[idx] = row.model_copy(update={"name": req.name.strip() or row.name, "updated_at": datetime.now(UTC)})
            self._save_watchlists(rows)
            return rows[idx]
        raise FileNotFoundError(watchlist_id)

    def delete_watchlist(self, watchlist_id: str) -> None:
        rows = self._read_watchlists()
        next_rows = [row for row in rows if row.id != watchlist_id]
        if len(next_rows) == len(rows):
            raise FileNotFoundError(watchlist_id)
        self._save_watchlists(next_rows)

    def add_watchlist_item(self, watchlist_id: str, req: WatchlistItemCreateRequest) -> Watchlist:
        rows = self._read_watchlists()
        for idx, row in enumerate(rows):
            if row.id != watchlist_id:
                continue
            symbol = req.symbol.strip().upper()
            if any(item.symbol.upper() == symbol and item.market == req.market for item in row.items):
                return row
            added_price = None
            added_price_estimated = False
            try:
                meta = self.analysis_engine.data_service.get_symbol_metadata(symbol, req.market)
                combined = self.analysis_engine.analyze_combined(
                    ticker=symbol,
                    market=req.market.value,
                    window="1y",
                    strategy_mode="balanced",
                )
                added_price = float(combined.indicator_summary.get("close", 0.0)) or None
                added_price_estimated = added_price is not None
                company_name = str(combined.indicator_summary.get("name")) if combined.indicator_summary.get("name") else None
                sector = str(combined.indicator_summary.get("sector")) if combined.indicator_summary.get("sector") else None
                industry = str(combined.indicator_summary.get("industry")) if combined.indicator_summary.get("industry") else None
                exchange = self._resolve_exchange(symbol, req.market.value, meta.exchange if meta else None)
            except Exception:
                added_price = None
                added_price_estimated = False
                company_name = None
                sector = None
                industry = None
                exchange = self._resolve_exchange(symbol, req.market.value, None)

            item = WatchlistItem(
                watchlist_id=row.id,
                symbol=symbol,
                market=req.market,
                added_at=datetime.now(UTC),
                notes=req.notes,
                added_price=added_price,
                added_price_estimated=added_price_estimated,
                company_name=company_name,
                sector=sector,
                industry=industry,
                exchange=exchange,
            )
            updated = row.model_copy(update={"items": [*row.items, item], "updated_at": datetime.now(UTC)})
            rows[idx] = updated
            self._save_watchlists(rows)
            return updated
        raise FileNotFoundError(watchlist_id)

    def remove_watchlist_item(self, watchlist_id: str, symbol: str, market: str) -> Watchlist:
        rows = self._read_watchlists()
        symbol_upper = symbol.strip().upper()
        for idx, row in enumerate(rows):
            if row.id != watchlist_id:
                continue
            items = [it for it in row.items if not (it.symbol.upper() == symbol_upper and it.market.value == market)]
            updated = row.model_copy(update={"items": items, "updated_at": datetime.now(UTC)})
            rows[idx] = updated
            self._save_watchlists(rows)
            return updated
        raise FileNotFoundError(watchlist_id)

    # Rules
    def list_alert_rules(
        self,
        *,
        symbol: str | None = None,
        watchlist_id: str | None = None,
        severity: str | None = None,
        enabled: bool | None = None,
    ) -> list[AlertRule]:
        rows = self._read_rules()
        filtered = rows
        if symbol:
            upper = symbol.strip().upper()
            filtered = [
                row
                for row in filtered
                if (row.symbol and row.symbol.upper() == upper) or row.scope_ref.upper() == upper
            ]
        if watchlist_id:
            filtered = [row for row in filtered if row.scope_type.value == "watchlist" and row.scope_ref == watchlist_id]
        if severity:
            filtered = [row for row in filtered if row.severity.value == severity]
        if enabled is not None:
            filtered = [row for row in filtered if row.is_enabled is enabled]
        return sorted(filtered, key=lambda row: row.updated_at, reverse=True)

    def create_alert_rule(self, req: AlertRuleCreateRequest) -> AlertRule:
        rows = self._read_rules()
        now = datetime.now(UTC)
        row = AlertRule(
            id=str(uuid4()),
            scope_type=req.scope_type,
            scope_ref=req.scope_ref,
            market=req.market,
            symbol=req.symbol.upper() if req.symbol else None,
            name=req.name.strip() or "Alert Rule",
            rule_type=req.rule_type,
            parameters=req.parameters,
            timeframe=req.timeframe,
            severity=req.severity,
            color=req.color,
            is_enabled=req.is_enabled,
            notification_enabled=req.notification_enabled,
            notify_email=req.notify_email,
            scanner_category=req.scanner_category,
            watchlist_id=req.watchlist_id,
            shortlisted_by=req.shortlisted_by,
            created_by=req.created_by,
            cooldown_minutes=req.cooldown_minutes,
            created_at=now,
            updated_at=now,
        )
        rows.append(row)
        self._save_rules(rows)
        return row

    def update_alert_rule(self, rule_id: str, req: AlertRuleUpdateRequest) -> AlertRule:
        rows = self._read_rules()
        for idx, row in enumerate(rows):
            if row.id != rule_id:
                continue
            payload = row.model_dump()
            if req.name is not None:
                payload["name"] = req.name.strip() or row.name
            if req.parameters is not None:
                payload["parameters"] = req.parameters
            if req.severity is not None:
                payload["severity"] = req.severity
            if req.color is not None:
                payload["color"] = req.color
            if req.is_enabled is not None:
                payload["is_enabled"] = req.is_enabled
            if req.timeframe is not None:
                payload["timeframe"] = req.timeframe
            if req.notification_enabled is not None:
                payload["notification_enabled"] = req.notification_enabled
            if req.notify_email is not None:
                payload["notify_email"] = req.notify_email
            if req.scanner_category is not None:
                payload["scanner_category"] = req.scanner_category
            if req.watchlist_id is not None:
                payload["watchlist_id"] = req.watchlist_id
            if req.shortlisted_by is not None:
                payload["shortlisted_by"] = req.shortlisted_by
            if req.created_by is not None:
                payload["created_by"] = req.created_by
            if req.cooldown_minutes is not None:
                payload["cooldown_minutes"] = req.cooldown_minutes
            payload["updated_at"] = datetime.now(UTC)
            updated = AlertRule.model_validate(payload)
            rows[idx] = updated
            self._save_rules(rows)
            return updated
        raise FileNotFoundError(rule_id)

    def delete_alert_rule(self, rule_id: str) -> None:
        rows = self._read_rules()
        next_rows = [row for row in rows if row.id != rule_id]
        if len(next_rows) == len(rows):
            raise FileNotFoundError(rule_id)
        self._save_rules(next_rows)

    # Schedules
    def list_schedules(self) -> list[MonitoringSchedule]:
        self._ensure_default_schedule()
        return self._read_schedules()

    def create_schedule(self, req: MonitoringScheduleCreateRequest) -> MonitoringSchedule:
        rows = self._read_schedules()
        now = datetime.now(UTC)
        interval = self._normalize_interval(req.interval or req.frequency)
        mode = "manual" if interval == "manual" else "auto"
        row = MonitoringSchedule(
            id=str(uuid4()),
            name=req.name.strip() or "Monitoring Schedule",
            market=req.market,
            frequency=interval,
            watchlist_id=req.watchlist_id,
            symbols=[sym.strip().upper() for sym in req.symbols],
            category=req.category,
            duration=req.duration,
            max_results=req.max_results,
            is_enabled=req.is_enabled,
            mode=mode,
            interval=interval,
            created_at=now,
            updated_at=now,
            last_run_at=None,
            next_run_at=self._next_run_time(interval, now),
        )
        rows.append(row)
        self._save_schedules(rows)
        return row

    def update_schedule(self, schedule_id: str, req: MonitoringScheduleUpdateRequest) -> MonitoringSchedule:
        rows = self._read_schedules()
        for idx, row in enumerate(rows):
            if row.id != schedule_id:
                continue
            payload = row.model_dump()
            for key in ("name", "watchlist_id", "category", "duration", "max_results", "is_enabled", "mode"):
                value = getattr(req, key)
                if value is not None:
                    payload[key] = value
            interval = self._normalize_interval(req.interval or req.frequency or payload.get("interval"))
            payload["interval"] = interval
            payload["frequency"] = interval
            if interval == "manual":
                payload["mode"] = "manual"
                payload["next_run_at"] = None
            else:
                payload["mode"] = "auto"
                payload["next_run_at"] = self._next_run_time(interval, datetime.now(UTC))
            if req.symbols is not None:
                payload["symbols"] = [sym.strip().upper() for sym in req.symbols]
            payload["updated_at"] = datetime.now(UTC)
            updated = MonitoringSchedule.model_validate(payload)
            rows[idx] = updated
            self._save_schedules(rows)
            return updated
        raise FileNotFoundError(schedule_id)

    def delete_schedule(self, schedule_id: str) -> None:
        rows = self._read_schedules()
        next_rows = [row for row in rows if row.id != schedule_id]
        if len(next_rows) == len(rows):
            raise FileNotFoundError(schedule_id)
        self._save_schedules(next_rows)

    # Events
    def list_alert_events(
        self,
        *,
        status: AlertEventStatus | None = None,
        severity: str | None = None,
        symbol: str | None = None,
    ) -> list[AlertEvent]:
        rows = self._read_events()
        filtered = rows
        if status is not None:
            filtered = [row for row in filtered if row.status == status]
        if severity is not None:
            filtered = [row for row in filtered if row.severity.value == severity]
        if symbol is not None:
            filtered = [row for row in filtered if row.symbol.upper() == symbol.upper()]
        return sorted(filtered, key=lambda row: row.timestamp, reverse=True)

    def update_event_status(self, event_id: str, req: AlertEventStatusUpdateRequest) -> AlertEvent:
        rows = self._read_events()
        for idx, row in enumerate(rows):
            if row.id != event_id:
                continue
            updated = row.model_copy(update={"status": req.status})
            rows[idx] = updated
            self._save_events(rows)
            return updated
        raise FileNotFoundError(event_id)

    def _symbols_for_rule(self, rule: AlertRule) -> list[str]:
        if rule.scope_type.value == "symbol" and rule.symbol:
            return [rule.symbol.upper()]
        watchlists = self._read_watchlists()
        for watchlist in watchlists:
            if watchlist.id == rule.scope_ref:
                return [item.symbol.upper() for item in watchlist.items if item.market == rule.market]
        return []

    @staticmethod
    def _alert_color_for_severity(severity: str) -> str:
        if severity == "critical":
            return "red"
        if severity == "important":
            return "orange"
        if severity == "info":
            return "blue"
        return "yellow"

    def suggest_alert_profile(self, req: AlertProfileSuggestRequest) -> AlertProfileSuggestionResponse:
        symbol = req.symbol.strip().upper()
        category = req.scanner_category.value

        def mk_rule(
            temp_id: str,
            name: str,
            rule_type: AlertRuleType,
            parameters: dict,
            severity: str,
            rationale: str,
            cooldown_minutes: int = 60,
        ) -> AlertProfileSuggestionRule:
            return AlertProfileSuggestionRule(
                temp_id=temp_id,
                name=name,
                rule_type=rule_type,
                parameters=parameters,
                severity=severity,
                color=self._alert_color_for_severity(severity),
                rationale=rationale,
                cooldown_minutes=cooldown_minutes,
            )

        by_category: dict[str, list[AlertProfileSuggestionRule]] = {
            "trend_mode": [
                mk_rule("near_ema20", f"{symbol} near EMA20 pullback", AlertRuleType.NEAR_EMA20, {"threshold_pct": 3}, "watch", "Tracks continuation pullbacks to EMA20.", 30),
                mk_rule("near_ema50", f"{symbol} near EMA50 pullback", AlertRuleType.NEAR_EMA50, {"threshold_pct": 5}, "watch", "Tracks deeper continuation pullbacks to EMA50.", 45),
                mk_rule("dynamics_weakening", f"{symbol} dynamics weakening", AlertRuleType.DYNAMICS_STATE_IS, {"state": "weakening", "category": "momentum_mode"}, "important", "Signals momentum quality deterioration.", 30),
                mk_rule("new_breakout_high", f"{symbol} new breakout high", AlertRuleType.NEW_BREAKOUT_HIGH, {"lookback_bars": 55}, "important", "Confirms fresh expansion highs.", 30),
                mk_rule("blowoff_warning", f"{symbol} blowoff extension warning", AlertRuleType.BLOWOFF_EXTENSION_WARNING, {}, "critical", "Warns when extension reaches blowoff state.", 20),
            ],
            "momentum_mode": [
                mk_rule("near_ema20", f"{symbol} near EMA20 pullback", AlertRuleType.NEAR_EMA20, {"threshold_pct": 3}, "watch", "Tracks continuation pullbacks to EMA20.", 30),
                mk_rule("near_ema50", f"{symbol} near EMA50 pullback", AlertRuleType.NEAR_EMA50, {"threshold_pct": 5}, "watch", "Tracks deeper continuation pullbacks to EMA50.", 45),
                mk_rule("dynamics_weakening", f"{symbol} dynamics weakening", AlertRuleType.DYNAMICS_STATE_IS, {"state": "weakening", "category": "momentum_mode"}, "important", "Signals momentum quality deterioration.", 30),
                mk_rule("new_breakout_high", f"{symbol} new breakout high", AlertRuleType.NEW_BREAKOUT_HIGH, {"lookback_bars": 55}, "important", "Confirms fresh expansion highs.", 30),
                mk_rule("blowoff_warning", f"{symbol} blowoff extension warning", AlertRuleType.BLOWOFF_EXTENSION_WARNING, {}, "critical", "Warns when extension reaches blowoff state.", 20),
            ],
            "build_up": [
                mk_rule("reclaim_ema200", f"{symbol} reclaim EMA200", AlertRuleType.RECLAIM_EMA200, {"max_bars_since_reclaim": 5}, "important", "Detects early regime reclaim phase.", 30),
                mk_rule("near_ema200", f"{symbol} near EMA200 zone", AlertRuleType.NEAR_EMA200, {"threshold_pct": 5}, "watch", "Tracks proximity to major rebuild anchor.", 45),
                mk_rule("resistance_tests", f"{symbol} resistance tests >= 3", AlertRuleType.RESISTANCE_TEST_COUNT_GTE, {"count": 3}, "watch", "Detects repeated pressure under resistance.", 60),
                mk_rule("volume_expand", f"{symbol} volume ratio 20 >= 1.5", AlertRuleType.VOLUME_RATIO_20_GTE, {"value": 1.5}, "important", "Tracks volume confirmation during build-up.", 30),
                mk_rule("fib_confluence", f"{symbol} fib/EMA confluence reached", AlertRuleType.FIB_EMA_CONFLUENCE_REACHED, {"max_distance_pct": 1.5}, "important", "Signals confluence test zone is reached.", 45),
            ],
            "value_rebuild": [
                mk_rule("near_ema200", f"{symbol} near EMA200 support", AlertRuleType.NEAR_EMA200, {"threshold_pct": 5}, "watch", "Tracks value rebuild around EMA200.", 45),
                mk_rule("fib_confluence", f"{symbol} fib/EMA support confluence", AlertRuleType.FIB_EMA_CONFLUENCE_REACHED, {"max_distance_pct": 1.5}, "important", "Detects confluence support interaction.", 45),
                mk_rule("dynamics_improving", f"{symbol} dynamics improving", AlertRuleType.DYNAMICS_STATE_IS, {"state": "improving", "category": "value_rebuild"}, "important", "Confirms rebuild momentum improvement.", 30),
                mk_rule("new_breakout_high", f"{symbol} resistance reclaim breakout", AlertRuleType.NEW_BREAKOUT_HIGH, {"lookback_bars": 34}, "important", "Captures resistance reclaim breakout.", 30),
                mk_rule("volume_expand", f"{symbol} volume ratio 20 >= 1.5", AlertRuleType.VOLUME_RATIO_20_GTE, {"value": 1.5}, "watch", "Tracks participation during rebuild.", 30),
            ],
            "overextended": [
                mk_rule("near_ema20", f"{symbol} pullback to EMA20", AlertRuleType.NEAR_EMA20, {"threshold_pct": 3}, "watch", "Tracks first pullback from extended move.", 30),
                mk_rule("near_ema50", f"{symbol} pullback to EMA50", AlertRuleType.NEAR_EMA50, {"threshold_pct": 5}, "important", "Tracks deeper mean-reversion pullback.", 45),
                mk_rule("blowoff_warning", f"{symbol} blowoff extension warning", AlertRuleType.BLOWOFF_EXTENSION_WARNING, {}, "critical", "Warns when extension becomes unstable.", 20),
                mk_rule("dynamics_weakening", f"{symbol} dynamics weakening", AlertRuleType.DYNAMICS_STATE_IS, {"state": "weakening", "category": "momentum_mode"}, "important", "Signals extension momentum deterioration.", 30),
            ],
        }

        rules = by_category.get(category, by_category["trend_mode"])
        return AlertProfileSuggestionResponse(
            symbol=symbol,
            market=req.market,
            scanner_category=req.scanner_category,
            watchlist_id=req.watchlist_id,
            shortlisted_by=req.shortlisted_by,
            created_by=req.created_by,
            rules=rules,
        )

    def apply_alert_profile(self, req: AlertProfileApplyRequest) -> list[AlertRule]:
        created: list[AlertRule] = []
        for suggestion in req.rules:
            if not suggestion.selected:
                continue
            payload = AlertRuleCreateRequest(
                scope_type=req.scope_type,
                scope_ref=req.scope_ref,
                market=req.market,
                symbol=req.symbol.upper(),
                name=suggestion.name,
                rule_type=suggestion.rule_type,
                parameters=suggestion.parameters,
                timeframe=suggestion.timeframe,
                severity=suggestion.severity,
                color=suggestion.color,
                is_enabled=suggestion.is_enabled,
                notification_enabled=req.notification_enabled,
                notify_email=req.notify_email,
                scanner_category=req.scanner_category,
                watchlist_id=req.watchlist_id,
                shortlisted_by=req.shortlisted_by,
                created_by=req.created_by,
                cooldown_minutes=suggestion.cooldown_minutes,
            )
            created.append(self.create_alert_rule(payload))
        return created

    @staticmethod
    def _dedupe_event_key(event: AlertEvent) -> str:
        if "state" in event.trigger_context:
            return f"state:{event.trigger_context.get('state')}"
        if "ema" in event.trigger_context:
            return f"ema:{event.trigger_context.get('ema')}"
        if event.signal_type:
            return f"signal:{event.signal_type.value}"
        if event.triggered_value is None:
            return "none"
        return f"value:{event.triggered_value}"

    @staticmethod
    def _to_float(value: float | str | None) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None

    def _event_meaningfully_changed(self, latest: AlertEvent, current: AlertEvent) -> bool:
        if self._dedupe_event_key(latest) != self._dedupe_event_key(current):
            return True
        if latest.signal_type != current.signal_type:
            return True
        if latest.message != current.message:
            return True
        prev_num = self._to_float(latest.triggered_value)
        cur_num = self._to_float(current.triggered_value)
        if prev_num is None or cur_num is None:
            return latest.triggered_value != current.triggered_value
        # Prevent spam for near-identical recurring values; allow through once value changes materially.
        tolerance = max(0.25, abs(prev_num) * 0.02)
        return abs(cur_num - prev_num) > tolerance

    def _event_allowed_by_cooldown(self, rule: AlertRule, event: AlertEvent, existing_events: list[AlertEvent]) -> bool:
        cooldown_minutes = max(0, int(rule.cooldown_minutes))
        if cooldown_minutes == 0:
            return True
        candidates = [row for row in existing_events if row.alert_rule_id == rule.id and row.symbol.upper() == event.symbol.upper()]
        if not candidates:
            return True
        latest = max(candidates, key=lambda row: row.timestamp)
        event.last_triggered_at = latest.timestamp
        elapsed_seconds = (event.timestamp - latest.timestamp).total_seconds()
        if elapsed_seconds >= cooldown_minutes * 60:
            return True
        # Allow state/meaning changes through even inside cooldown.
        return self._event_meaningfully_changed(latest, event)

    @staticmethod
    def _build_alert_semantics(
        *,
        rule_type: AlertRuleType,
        trend_state: str | None,
        score_dynamics_state: str | None,
        scanner_category: str | None,
    ) -> tuple[AlertSignalType, str, str]:
        trend = (trend_state or "").lower()
        dynamics = (score_dynamics_state or "").lower()
        category = (scanner_category or "").lower()

        if rule_type in {AlertRuleType.CROSS_BELOW_EMA100, AlertRuleType.CROSS_BELOW_EMA200, AlertRuleType.BLOWOFF_EXTENSION_WARNING}:
            return (
                AlertSignalType.RISK_WARNING,
                "Structure may be weakening or overly extended versus trend anchors.",
                "Review risk controls and open Analysis before adding risk.",
            )
        if rule_type in {AlertRuleType.PRICE_GTE, AlertRuleType.PRICE_LTE, AlertRuleType.RSI14_GTE, AlertRuleType.RSI14_LTE}:
            return (
                AlertSignalType.INFO,
                "A monitoring threshold was reached.",
                "Open Analysis to confirm context. This is not an automatic signal.",
            )
        if rule_type in {AlertRuleType.NEW_BREAKOUT_HIGH, AlertRuleType.CROSS_ABOVE_EMA100, AlertRuleType.CROSS_ABOVE_EMA200}:
            return (
                AlertSignalType.MOMENTUM_WATCH,
                "Price is showing expansion or reclaim behavior.",
                "Check continuation quality, volume confirmation, and extension risk.",
            )
        if rule_type in {AlertRuleType.NEAR_EMA20, AlertRuleType.NEAR_EMA50, AlertRuleType.NEAR_EMA100, AlertRuleType.NEAR_EMA200}:
            if trend in {"bullish_trend", "weakening_trend"} and dynamics in {"improving", "accelerating"}:
                return (
                    AlertSignalType.OPPORTUNITY,
                    "Price is near a key EMA in a constructive trend, which may indicate pullback opportunity context.",
                    "Open Analysis. This is a setup watch, not an automatic buy signal.",
                )
            if trend in {"damaged_trend", "sideways"}:
                return (
                    AlertSignalType.RISK_WARNING,
                    "Price is near a key EMA but structure is weak, so this is caution context.",
                    "Treat as risk-monitoring; wait for structure improvement.",
                )
            return (
                AlertSignalType.INFO,
                "Price is near a key EMA and may be entering an interaction zone.",
                "Open Analysis and validate trend, trigger, and score dynamics.",
            )
        if rule_type in {AlertRuleType.RECLAIM_EMA200, AlertRuleType.FIB_EMA_CONFLUENCE_REACHED, AlertRuleType.RESISTANCE_TEST_COUNT_GTE}:
            return (
                AlertSignalType.OPPORTUNITY,
                "A rebuild/confluence condition was detected and may indicate setup development.",
                "Open Analysis and confirm regime, trigger quality, and room to resistance.",
            )
        if rule_type in {AlertRuleType.SCANNER_TOP_N, AlertRuleType.DYNAMICS_STATE_IS, AlertRuleType.VOLUME_RATIO_20_GTE}:
            if dynamics in {"accelerating", "improving"} or category in {"momentum_mode", "trend_mode"}:
                return (
                    AlertSignalType.MOMENTUM_WATCH,
                    "Momentum quality is improving in the monitored context.",
                    "Review continuation conditions and extension state in Analysis.",
                )
            return (
                AlertSignalType.EXIT_WATCH,
                "Momentum quality changed and may impact continuation quality.",
                "Review open risk and monitor for structure deterioration.",
            )
        return (
            AlertSignalType.INFO,
            "Monitoring condition triggered.",
            "Open Analysis. This is not an automatic trade signal.",
        )

    def _append_event_if_allowed(
        self,
        *,
        rule: AlertRule,
        event: AlertEvent | None,
        existing_events: list[AlertEvent],
        created_events: list[AlertEvent],
    ) -> bool:
        if event is None:
            return False
        if not self._event_allowed_by_cooldown(rule, event, [*existing_events, *created_events]):
            return False
        created_events.append(event)
        return True

    def _build_alert_event(
        self,
        *,
        rule: AlertRule,
        symbol: str,
        triggered_value: float | str | None,
        message: str,
        trigger_context: dict,
        scanner_context: dict,
        analysis_context: dict,
    ) -> AlertEvent:
        trend_state = str(analysis_context.get("trend_state", ""))
        score_dynamics_state = str(analysis_context.get("score_dynamics_state", "") or scanner_context.get("score_dynamics_state", ""))
        signal_type, plain_english_meaning, suggested_action = self._build_alert_semantics(
            rule_type=rule.rule_type,
            trend_state=trend_state,
            score_dynamics_state=score_dynamics_state,
            scanner_category=rule.scanner_category.value if rule.scanner_category else None,
        )
        notification_status = "pending_notification" if rule.notification_enabled else "disabled"
        return AlertEvent(
            id=str(uuid4()),
            alert_rule_id=rule.id,
            timestamp=datetime.now(UTC),
            symbol=symbol,
            market=rule.market,
            triggered_value=triggered_value,
            trigger_context=trigger_context,
            severity=rule.severity,
            status=AlertEventStatus.NEW,
            message=message,
            watchlist_id=rule.watchlist_id if rule.watchlist_id else (rule.scope_ref if rule.scope_type.value == "watchlist" else None),
            scanner_category=rule.scanner_category,
            shortlisted_by=rule.shortlisted_by,
            notification_status=notification_status,
            notified_to=rule.notify_email if rule.notification_enabled else None,
            notified_at=None,
            scanner_context=scanner_context,
            analysis_context=analysis_context,
            signal_type=signal_type,
            plain_english_meaning=plain_english_meaning,
            suggested_action=suggested_action,
            last_triggered_at=None,
        )

    def _evaluate_symbol_rule(self, rule: AlertRule, symbol: str) -> AlertEvent | None:
        combined = self.analysis_engine.analyze_combined(
            ticker=symbol,
            market=rule.market.value,
            window="1y",
            strategy_mode="balanced",
        )
        snapshot = combined.indicator_summary
        close = float(snapshot.get("close", 0.0))
        ema20 = float(snapshot.get("ema_20", close))
        ema50 = float(snapshot.get("ema_50", close))
        ema200 = float(snapshot.get("ema_200", close))
        ema100 = float(snapshot.get("ema_100", close))
        rsi14 = float(snapshot.get("rsi_14", 0.0))
        vol_ratio = float(snapshot.get("volume", {}).get("volume_ratio", 0.0))
        regime = combined.regime
        setup = combined.setup_interpretation
        chartmap = combined.chartmap
        score_dynamics_state = combined.entry_gate.score_dynamics_state or "stable"

        prev_close = close
        prev_ema100 = ema100
        prev_ema200 = ema200
        if len(combined.chart.candles) >= 2:
            prev_close = float(combined.chart.candles[-2].close)
        if len(combined.chart.ema_100) >= 2:
            prev_ema100 = float(combined.chart.ema_100[-2].value)
        if len(combined.chart.ema_200) >= 2:
            prev_ema200 = float(combined.chart.ema_200[-2].value)

        params = rule.parameters
        threshold = float(params.get("threshold_pct", 3.0))
        value = float(params.get("value", 0.0)) if "value" in params else None
        count_threshold = int(params.get("count", 2))
        last_low = float(combined.chart.candles[-1].low) if combined.chart.candles else close
        last_high = float(combined.chart.candles[-1].high) if combined.chart.candles else close

        # Weekly EMA context (deterministic from available daily candles in analysis payload window)
        weekly_ema100 = ema100
        weekly_ema200 = ema200
        prev_weekly_ema100 = prev_ema100
        prev_weekly_ema200 = prev_ema200
        prev_week_close = prev_close
        if len(combined.chart.candles) >= 40:
            weekly_df = pd.DataFrame(
                {
                    "date": [c.date for c in combined.chart.candles],
                    "close": [float(c.close) for c in combined.chart.candles],
                }
            )
            weekly_df["date"] = pd.to_datetime(weekly_df["date"])
            weekly_df = weekly_df.set_index("date").resample("W-FRI").last().dropna()
            if len(weekly_df) >= 5:
                ema100_series = weekly_df["close"].ewm(span=100, adjust=False).mean()
                ema200_series = weekly_df["close"].ewm(span=200, adjust=False).mean()
                weekly_ema100 = float(ema100_series.iloc[-1])
                weekly_ema200 = float(ema200_series.iloc[-1])
                prev_week_close = float(weekly_df["close"].iloc[-2]) if len(weekly_df) >= 2 else prev_close
                prev_weekly_ema100 = float(ema100_series.iloc[-2]) if len(ema100_series) >= 2 else weekly_ema100
                prev_weekly_ema200 = float(ema200_series.iloc[-2]) if len(ema200_series) >= 2 else weekly_ema200

        if rule.rule_type == AlertRuleType.NEAR_EMA20:
            dist = abs((close - ema20) / max(ema20, 0.01) * 100.0)
            if dist <= threshold:
                return self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=round(dist, 2),
                    message=f"{symbol} is within {dist:.2f}% of EMA20",
                    trigger_context={"distance_pct": round(dist, 2), "ema": 20},
                    scanner_context={},
                    analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                )
        elif rule.rule_type == AlertRuleType.NEAR_EMA50:
            dist = abs((close - ema50) / max(ema50, 0.01) * 100.0)
            if dist <= threshold:
                return self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=round(dist, 2),
                    message=f"{symbol} is within {dist:.2f}% of EMA50",
                    trigger_context={"distance_pct": round(dist, 2), "ema": 50},
                    scanner_context={},
                    analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                )
        elif rule.rule_type == AlertRuleType.NEAR_EMA100:
            dist = abs((close - ema100) / max(ema100, 0.01) * 100.0)
            if dist <= threshold:
                return self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=round(dist, 2),
                    message=f"{symbol} is within {dist:.2f}% of EMA100",
                    trigger_context={"distance_pct": round(dist, 2), "ema": 100},
                    scanner_context={},
                    analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                )
        elif rule.rule_type == AlertRuleType.NEAR_EMA200:
            dist = abs((close - ema200) / max(ema200, 0.01) * 100.0)
            if dist <= threshold:
                return self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=round(dist, 2),
                    message=f"{symbol} is within {dist:.2f}% of EMA200",
                    trigger_context={"distance_pct": round(dist, 2), "ema": 200},
                    scanner_context={},
                    analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                )
        elif rule.rule_type == AlertRuleType.CROSS_ABOVE_EMA100:
            if prev_close <= prev_ema100 and close > ema100:
                return self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=close,
                    message=f"{symbol} crossed above EMA100",
                    trigger_context={"prev_close": prev_close, "prev_ema100": prev_ema100, "close": close, "ema100": ema100},
                    scanner_context={},
                    analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                )
        elif rule.rule_type == AlertRuleType.CROSS_ABOVE_EMA200:
            if prev_close <= prev_ema200 and close > ema200:
                return self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=close,
                    message=f"{symbol} crossed above EMA200",
                    trigger_context={"prev_close": prev_close, "prev_ema200": prev_ema200, "close": close, "ema200": ema200},
                    scanner_context={},
                    analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                )
        elif rule.rule_type == AlertRuleType.CROSS_BELOW_EMA100:
            if prev_close >= prev_ema100 and close < ema100:
                return self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=close,
                    message=f"{symbol} crossed below EMA100",
                    trigger_context={"prev_close": prev_close, "prev_ema100": prev_ema100, "close": close, "ema100": ema100},
                    scanner_context={},
                    analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                )
        elif rule.rule_type == AlertRuleType.CROSS_BELOW_EMA200:
            if prev_close >= prev_ema200 and close < ema200:
                return self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=close,
                    message=f"{symbol} crossed below EMA200",
                    trigger_context={"prev_close": prev_close, "prev_ema200": prev_ema200, "close": close, "ema200": ema200},
                    scanner_context={},
                    analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                )
        elif rule.rule_type == AlertRuleType.PRICE_GTE and value is not None and close >= value:
            return self._build_alert_event(
                rule=rule,
                symbol=symbol,
                triggered_value=close,
                message=f"{symbol} price {close:.2f} >= {value:.2f}",
                trigger_context={"price": close, "threshold": value},
                scanner_context={},
                analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
            )
        elif rule.rule_type == AlertRuleType.PRICE_LTE and value is not None and close <= value:
            return self._build_alert_event(
                rule=rule,
                symbol=symbol,
                triggered_value=close,
                message=f"{symbol} price {close:.2f} <= {value:.2f}",
                trigger_context={"price": close, "threshold": value},
                scanner_context={},
                analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
            )
        elif rule.rule_type == AlertRuleType.LOW_LTE and value is not None and last_low <= value:
            return self._build_alert_event(
                rule=rule,
                symbol=symbol,
                triggered_value=round(last_low, 2),
                message=f"{symbol} daily low {last_low:.2f} <= {value:.2f}",
                trigger_context={"daily_low": round(last_low, 2), "threshold": value},
                scanner_context={},
                analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
            )
        elif rule.rule_type == AlertRuleType.HIGH_GTE and value is not None and last_high >= value:
            return self._build_alert_event(
                rule=rule,
                symbol=symbol,
                triggered_value=round(last_high, 2),
                message=f"{symbol} daily high {last_high:.2f} >= {value:.2f}",
                trigger_context={"daily_high": round(last_high, 2), "threshold": value},
                scanner_context={},
                analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
            )
        elif rule.rule_type == AlertRuleType.TREND_STATE_IS:
            target = str(params.get("state", "bullish_trend"))
            if setup.trend_state == target:
                return self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=setup.trend_state,
                    message=f"{symbol} trend_state became {setup.trend_state}",
                    trigger_context={"trend_state": setup.trend_state},
                    scanner_context={},
                    analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                )
        elif rule.rule_type == AlertRuleType.RECLAIM_EMA200:
            if regime.bars_since_reclaim is not None and regime.bars_since_reclaim <= int(params.get("max_bars_since_reclaim", 5)):
                return self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=regime.bars_since_reclaim,
                    message=f"{symbol} reclaimed EMA200 ({regime.bars_since_reclaim} bars since reclaim)",
                    trigger_context={"bars_since_reclaim": regime.bars_since_reclaim},
                    scanner_context={},
                    analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                )
        elif rule.rule_type == AlertRuleType.VOLUME_RATIO_20_GTE and value is not None and vol_ratio >= value:
            return self._build_alert_event(
                rule=rule,
                symbol=symbol,
                triggered_value=round(vol_ratio, 2),
                message=f"{symbol} volume ratio 20 {vol_ratio:.2f} >= {value:.2f}",
                trigger_context={"volume_ratio_20": round(vol_ratio, 2), "threshold": value},
                scanner_context={},
                analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
            )
        elif rule.rule_type == AlertRuleType.RSI14_LTE and value is not None and rsi14 <= value:
            return self._build_alert_event(
                rule=rule,
                symbol=symbol,
                triggered_value=round(rsi14, 2),
                message=f"{symbol} RSI14 {rsi14:.2f} <= {value:.2f}",
                trigger_context={"rsi_14": round(rsi14, 2), "threshold": value},
                scanner_context={},
                analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
            )
        elif rule.rule_type == AlertRuleType.RSI14_GTE and value is not None and rsi14 >= value:
            return self._build_alert_event(
                rule=rule,
                symbol=symbol,
                triggered_value=round(rsi14, 2),
                message=f"{symbol} RSI14 {rsi14:.2f} >= {value:.2f}",
                trigger_context={"rsi_14": round(rsi14, 2), "threshold": value},
                scanner_context={},
                analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
            )
        elif rule.rule_type == AlertRuleType.RESISTANCE_TEST_COUNT_GTE:
            count = int(snapshot.get("resistance_test_count", 0))
            if count >= count_threshold:
                return self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=count,
                    message=f"{symbol} resistance_test_count reached {count}",
                    trigger_context={"resistance_test_count": count, "threshold": count_threshold},
                    scanner_context={},
                    analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                )
        elif rule.rule_type == AlertRuleType.NEW_BREAKOUT_HIGH:
            lookback_bars = int(params.get("lookback_bars", 55))
            highs = [float(candle.high) for candle in combined.chart.candles]
            if len(highs) >= 2:
                prior_slice = highs[max(0, len(highs) - 1 - lookback_bars): len(highs) - 1]
                prior_high = max(prior_slice) if prior_slice else highs[-2]
                if close > prior_high:
                    return self._build_alert_event(
                        rule=rule,
                        symbol=symbol,
                        triggered_value=round(close, 2),
                        message=f"{symbol} printed a new breakout high above {prior_high:.2f}",
                        trigger_context={"close": round(close, 2), "prior_high": round(prior_high, 2), "lookback_bars": lookback_bars},
                        scanner_context={},
                        analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                    )
        elif rule.rule_type == AlertRuleType.BLOWOFF_EXTENSION_WARNING:
            if combined.location.extension_state == "blowoff_extension":
                return self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=combined.location.extension_state,
                    message=f"{symbol} entered blowoff extension state",
                    trigger_context={"extension_state": combined.location.extension_state},
                    scanner_context={},
                    analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                )
        elif rule.rule_type == AlertRuleType.FIB_EMA_CONFLUENCE_REACHED:
            max_distance = float(params.get("max_distance_pct", 1.5))
            distance = chartmap.distance_to_nearest_fib_pct
            has_confluence = bool(chartmap.fib_support_confluence or (chartmap.fib_ema_confluence_score or 0.0) >= 60.0)
            if has_confluence and distance is not None and distance <= max_distance:
                return self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=round(distance, 2),
                    message=f"{symbol} reached fib/EMA confluence zone ({distance:.2f}% from nearest fib)",
                    trigger_context={"distance_to_nearest_fib_pct": round(distance, 2), "max_distance_pct": max_distance},
                    scanner_context={"fib_ema_confluence_score": chartmap.fib_ema_confluence_score},
                    analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                )
        elif rule.rule_type == AlertRuleType.NEAR_WEEKLY_EMA100:
            dist = abs((close - weekly_ema100) / max(weekly_ema100, 0.01) * 100.0)
            if dist <= threshold:
                return self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=round(dist, 2),
                    message=f"{symbol} is within {dist:.2f}% of weekly EMA100",
                    trigger_context={"distance_pct": round(dist, 2), "ema": "weekly_100"},
                    scanner_context={},
                    analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                )
        elif rule.rule_type == AlertRuleType.NEAR_WEEKLY_EMA200:
            dist = abs((close - weekly_ema200) / max(weekly_ema200, 0.01) * 100.0)
            if dist <= threshold:
                return self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=round(dist, 2),
                    message=f"{symbol} is within {dist:.2f}% of weekly EMA200",
                    trigger_context={"distance_pct": round(dist, 2), "ema": "weekly_200"},
                    scanner_context={},
                    analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                )
        elif rule.rule_type == AlertRuleType.CROSS_ABOVE_WEEKLY_EMA100:
            if prev_week_close <= prev_weekly_ema100 and close > weekly_ema100:
                return self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=round(close, 2),
                    message=f"{symbol} crossed above weekly EMA100",
                    trigger_context={"prev_week_close": prev_week_close, "prev_weekly_ema100": prev_weekly_ema100, "close": close, "weekly_ema100": weekly_ema100},
                    scanner_context={},
                    analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                )
        elif rule.rule_type == AlertRuleType.CROSS_ABOVE_WEEKLY_EMA200:
            if prev_week_close <= prev_weekly_ema200 and close > weekly_ema200:
                return self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=round(close, 2),
                    message=f"{symbol} crossed above weekly EMA200",
                    trigger_context={"prev_week_close": prev_week_close, "prev_weekly_ema200": prev_weekly_ema200, "close": close, "weekly_ema200": weekly_ema200},
                    scanner_context={},
                    analysis_context={"trend_state": setup.trend_state, "score_dynamics_state": score_dynamics_state},
                )
        return None

    def _evaluate_scanner_rule(self, rule: AlertRule, symbols: list[str]) -> list[AlertEvent]:
        category = rule.parameters.get("category", "trend_mode")
        top_n = int(rule.parameters.get("top_n", 20))
        duration = rule.parameters.get("duration", "2y")
        req = ScannerRequest(
            market=rule.market,
            duration=duration,
            category=category,
            max_results=max(top_n, 20),
            universe_scope="watchlist" if rule.scope_type.value == "watchlist" else "capped_universe",
            symbol_overrides=symbols,
        )
        response = self.scanner_engine.scan(req)
        top = response.results[:top_n]
        top_symbols = {row.symbol.upper(): row for row in top}
        events: list[AlertEvent] = []
        for symbol in symbols:
            if symbol.upper() not in top_symbols:
                continue
            row = top_symbols[symbol.upper()]
            events.append(
                self._build_alert_event(
                    rule=rule,
                    symbol=symbol,
                    triggered_value=row.scanner_score,
                    message=f"{symbol} entered top {top_n} for {category.replace('_', ' ')}",
                    trigger_context={"rank_top_n": top_n, "category": category},
                    scanner_context={"scanner_score": row.scanner_score, "score_dynamics_state": row.score_dynamics_state},
                    analysis_context={"trend_state": row.trend_state, "score_dynamics_state": row.score_dynamics_state},
                )
            )
        return events

    def run_monitoring(self, req: MonitoringRunRequest) -> MonitoringRunSummary:
        started = datetime.now(UTC)
        started_monotonic = time.monotonic()
        if not self._run_lock.acquire(blocking=False):
            self._logger.info("monitoring skipped: previous run still active")
            return MonitoringRunSummary(
                started_at=started,
                finished_at=datetime.now(UTC),
                processed_rules=0,
                evaluated_symbols=0,
                events_created=0,
                partial_run=True,
                note="Monitoring run skipped because another run is still active.",
            )
        self._logger.info("monitoring started")
        rules = [rule for rule in self._read_rules() if rule.is_enabled]
        events = self._read_events()
        rules_all = self._read_rules()
        rules_index = {row.id: row for row in rules_all}
        created: list[AlertEvent] = []
        processed_rules = 0
        evaluated_symbols = 0
        partial = False
        note = None
        symbol_targets = self._build_symbol_targets(req)
        symbol_timeout_seconds = 8.0

        try:
            # Always run base symbol metric cycle, even when no rules match.
            symbols_processed = 0
            for symbol, market in symbol_targets:
                elapsed = time.monotonic() - started_monotonic
                if elapsed >= req.max_runtime_seconds:
                    partial = True
                    note = f"Monitoring partial run: runtime budget {req.max_runtime_seconds:.1f}s reached."
                    break
                per_symbol_start = time.monotonic()
                try:
                    scan = self.scanner_engine.scan(
                        ScannerRequest(
                            market=market,
                            duration="1y",
                            category="trend_mode",
                            max_results=20,
                            universe_scope="watchlist",
                            symbol_overrides=[symbol],
                            use_custom_rules=False,
                        )
                    )
                    row = scan.results[0] if scan.results else None
                    score = row.current_score if row is not None else 0.0
                    dynamics = row.score_dynamics_state if row is not None else "stable"
                    self._refresh_watchlist_metrics_for_symbol(
                        symbol,
                        market,
                        current_score=score,
                        score_dynamics_state=dynamics,
                    )
                    symbols_processed += 1
                except Exception as exc:
                    self._logger.warning("monitoring symbol refresh failed for %s: %s", symbol, exc)
                duration = time.monotonic() - per_symbol_start
                if duration > symbol_timeout_seconds:
                    self._logger.warning("monitoring symbol refresh slow for %s: %.2fs", symbol, duration)

            evaluated_symbols = symbols_processed

            for rule in rules:
                if req.market is not None and rule.market != req.market:
                    continue
                symbols = self._symbols_for_rule(rule)
                if req.watchlist_id is not None and rule.scope_ref != req.watchlist_id:
                    continue
                if req.symbols:
                    symbols = [sym for sym in symbols if sym.upper() in {s.upper() for s in req.symbols}]
                symbols = sorted(set(symbols))
                if len(symbols) > req.max_symbols_per_batch:
                    symbols = symbols[: req.max_symbols_per_batch]
                if not symbols:
                    continue

                elapsed = time.monotonic() - started_monotonic
                if elapsed >= req.max_runtime_seconds:
                    partial = True
                    note = f"Monitoring partial run: runtime budget {req.max_runtime_seconds:.1f}s reached."
                    break

                processed_rules += 1
                matched_for_rule = False
                if rule.rule_type in {AlertRuleType.SCANNER_TOP_N, AlertRuleType.DYNAMICS_STATE_IS}:
                    if rule.rule_type == AlertRuleType.SCANNER_TOP_N:
                        scanner_events = self._evaluate_scanner_rule(rule, symbols)
                        for event in scanner_events:
                            matched_for_rule = self._append_event_if_allowed(
                                rule=rule,
                                event=event,
                                existing_events=events,
                                created_events=created,
                            ) or matched_for_rule
                    else:
                        category = rule.parameters.get("category", "momentum_mode")
                        target_state = str(rule.parameters.get("state", "accelerating"))
                        req_scan = ScannerRequest(
                            market=rule.market,
                            duration=rule.parameters.get("duration", "1y"),
                            category=category,
                            max_results=100,
                            universe_scope="watchlist" if rule.scope_type.value == "watchlist" else "capped_universe",
                            symbol_overrides=symbols,
                        )
                        resp = self.scanner_engine.scan(req_scan)
                        for row in resp.results:
                            if row.score_dynamics_state != target_state:
                                continue
                            self._refresh_watchlist_metrics_for_symbol(
                                row.symbol,
                                rule.market,
                                current_score=row.current_score,
                                score_dynamics_state=row.score_dynamics_state,
                            )
                            matched_for_rule = self._append_event_if_allowed(
                                rule=rule,
                                event=self._build_alert_event(
                                    rule=rule,
                                    symbol=row.symbol,
                                    triggered_value=row.score_dynamics_state,
                                    message=f"{row.symbol} score dynamics became {row.score_dynamics_state}",
                                    trigger_context={"state": row.score_dynamics_state},
                                    scanner_context={"scanner_score": row.scanner_score},
                                    analysis_context={"trend_state": row.trend_state, "score_dynamics_state": row.score_dynamics_state},
                                ),
                                existing_events=events,
                                created_events=created,
                            ) or matched_for_rule
                    evaluated_symbols = max(evaluated_symbols, len(symbol_targets))
                    rule_payload = rules_index.get(rule.id).model_dump() if rules_index.get(rule.id) else rule.model_dump()
                    now_checked = datetime.now(UTC)
                    rule_payload["last_checked"] = now_checked
                    if matched_for_rule:
                        rule_payload["last_matched"] = now_checked
                    rules_index[rule.id] = AlertRule.model_validate(rule_payload)
                    continue

                for symbol in symbols:
                    event = self._evaluate_symbol_rule(rule, symbol)
                    evaluated_symbols = max(evaluated_symbols, len(symbol_targets))
                    matched_for_rule = self._append_event_if_allowed(
                        rule=rule,
                        event=event,
                        existing_events=events,
                        created_events=created,
                    ) or matched_for_rule

                rule_payload = rules_index.get(rule.id).model_dump() if rules_index.get(rule.id) else rule.model_dump()
                now_checked = datetime.now(UTC)
                rule_payload["last_checked"] = now_checked
                if matched_for_rule:
                    rule_payload["last_matched"] = now_checked
                rules_index[rule.id] = AlertRule.model_validate(rule_payload)

            if created:
                events.extend(created)
                self._save_events(events)
            # persist rule check metadata even if no event
            self._save_rules(list(rules_index.values()))

            # Update schedule run metadata if run was scoped by watchlist
            if req.watchlist_id is not None:
                schedules = self._read_schedules()
                changed = False
                for idx, schedule in enumerate(schedules):
                    if schedule.watchlist_id != req.watchlist_id:
                        continue
                    now = datetime.now(UTC)
                    schedules[idx] = schedule.model_copy(
                        update={
                            "last_run_at": now,
                            "next_run_at": self._next_run_time(schedule.interval or schedule.frequency, now),
                            "updated_at": now,
                        }
                    )
                    changed = True
                if changed:
                    self._save_schedules(schedules)

            finished = datetime.now(UTC)
            duration = (finished - started).total_seconds()
            self._logger.info(
                "monitoring finished: symbols processed=%s rules evaluated=%s events=%s duration=%.2fs",
                evaluated_symbols,
                processed_rules,
                len(created),
                duration,
            )
            return MonitoringRunSummary(
                started_at=started,
                finished_at=finished,
                processed_rules=processed_rules,
                evaluated_symbols=evaluated_symbols,
                events_created=len(created),
                partial_run=partial,
                note=note,
            )
        finally:
            self._run_lock.release()

    def run_due_schedules(self, max_runtime_seconds: float = 30.0) -> MonitoringRunSummary:
        self._ensure_default_schedule()
        all_schedules = self._read_schedules()
        schedules = [
            row
            for row in all_schedules
            if row.is_enabled and row.mode != "manual" and row.next_run_at is not None and row.next_run_at <= datetime.now(UTC)
        ]
        aggregate = MonitoringRunSummary(
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            processed_rules=0,
            evaluated_symbols=0,
            events_created=0,
            partial_run=False,
            note=None,
        )
        start_mono = time.monotonic()
        self._logger.info("due monitoring cycle started")
        for schedule in schedules:
            if time.monotonic() - start_mono >= max_runtime_seconds:
                aggregate.partial_run = True
                aggregate.note = "Due schedule run partial: runtime budget reached."
                break
            run_req = MonitoringRunRequest(
                market=schedule.market,
                watchlist_id=schedule.watchlist_id,
                symbols=schedule.symbols,
                max_runtime_seconds=max(5.0, max_runtime_seconds / max(1, len(schedules))),
            )
            summary = self.run_monitoring(run_req)
            aggregate.processed_rules += summary.processed_rules
            aggregate.evaluated_symbols += summary.evaluated_symbols
            aggregate.events_created += summary.events_created
            aggregate.partial_run = aggregate.partial_run or summary.partial_run
            now = datetime.now(UTC)
            updated_schedule = schedule.model_copy(
                update={
                    "last_run_at": now,
                    "next_run_at": self._next_run_time(schedule.interval or schedule.frequency, now),
                    "updated_at": now,
                }
            )
            all_schedules = [updated_schedule if row.id == schedule.id else row for row in all_schedules]
            self._save_schedules(all_schedules)
        aggregate.finished_at = datetime.now(UTC)
        self._logger.info(
            "due monitoring cycle finished: symbols processed=%s rules evaluated=%s events=%s duration=%.2fs",
            aggregate.evaluated_symbols,
            aggregate.processed_rules,
            aggregate.events_created,
            (aggregate.finished_at - aggregate.started_at).total_seconds(),
        )
        return aggregate
    @staticmethod
    def _compute_return_pct(current: float | None, reference: float | None) -> float | None:
        if current is None or reference is None or reference <= 0:
            return None
        return (current / reference - 1.0) * 100.0

    @staticmethod
    def _close_at_offset(closes: list[float], offset: int) -> float | None:
        if not closes:
            return None
        idx = len(closes) - 1 - offset
        if idx < 0:
            idx = 0
        return closes[idx]

    @staticmethod
    def _nearest_close_to_datetime(candles: list, ts: datetime) -> float | None:
        if not candles:
            return None
        best = min(
            candles,
            key=lambda candle: abs(
                datetime.combine(candle.date, datetime.min.time(), tzinfo=UTC).timestamp() - ts.timestamp()
            ),
        )
        return float(best.close)

    def _symbol_close_series(self, symbol: str, market) -> pd.Series:
        bundle = self.analysis_engine.data_service.get_market_data(
            symbol,
            market=market.value,
            period="2y",
            use_cache=False,
        )
        expected = normalize_symbol(symbol, market.value).upper()
        actual = str(getattr(bundle, "normalized_ticker", "") or "").upper()
        if actual and actual != expected:
            raise RuntimeError(f"symbol price mismatch: requested={expected} received={actual}")
        close = bundle.daily["close"].dropna().astype(float)
        if close.empty:
            raise RuntimeError(f"missing close series for {expected}")
        return close

    @staticmethod
    def _nearest_close_to_watch_time(close: pd.Series, ts: datetime) -> float | None:
        if close.empty:
            return None
        target = ts.astimezone(UTC) if ts.tzinfo else ts.replace(tzinfo=UTC)
        best_idx = min(
            close.index,
            key=lambda idx: abs(
                datetime.combine(idx.date(), datetime.min.time(), tzinfo=UTC).timestamp() - target.timestamp()
            ),
        )
        return float(close.loc[best_idx])

    def _refresh_watchlist_metrics_for_symbol(
        self,
        symbol: str,
        market,
        *,
        current_score: float,
        score_dynamics_state: str,
    ) -> None:
        watchlists = self._read_watchlists()
        changed = False
        now = datetime.now(UTC)
        try:
            combined = self.analysis_engine.analyze_combined(
                ticker=symbol,
                market=market.value,
                window="1y",
                strategy_mode="balanced",
            )
        except Exception:
            return

        try:
            close_series = self._symbol_close_series(symbol, market)
        except Exception as exc:
            self._logger.warning("watchlist metric price refresh failed for %s: %s", symbol, exc)
            return
        closes = [float(value) for value in close_series.tolist()]
        current_price = float(close_series.iloc[-1])
        ema200 = close_series.ewm(span=200, adjust=False).mean().iloc[-1]
        price_vs_ema200 = float((current_price - ema200) / max(float(ema200), 0.01) * 100.0)

        for wl_idx, watchlist in enumerate(watchlists):
            updated_items: list[WatchlistItem] = []
            item_changed = False
            for item in watchlist.items:
                if item.symbol.upper() != symbol.upper() or item.market != market:
                    updated_items.append(item)
                    continue
                added_price = item.added_price
                added_price_estimated = item.added_price_estimated
                if added_price is None:
                    estimated = self._nearest_close_to_watch_time(close_series, item.added_at)
                    if estimated is not None:
                        added_price = estimated
                        added_price_estimated = True
                        item_changed = True
                updated_item = item.model_copy(
                    update={
                        "added_price": added_price,
                        "added_price_estimated": added_price_estimated,
                        "current_price": current_price,
                        "pnl_since_added_pct": self._compute_return_pct(current_price, added_price),
                        "return_1m_pct": self._compute_return_pct(current_price, self._close_at_offset(closes, 21)),
                        "return_3m_pct": self._compute_return_pct(current_price, self._close_at_offset(closes, 63)),
                        "return_6m_pct": self._compute_return_pct(current_price, self._close_at_offset(closes, 126)),
                        "return_1y_pct": self._compute_return_pct(current_price, self._close_at_offset(closes, 252)),
                        "trend_state": combined.setup_interpretation.trend_state,
                        "score": current_score,
                        "score_dynamics_state": score_dynamics_state,
                        "price_vs_ema200_pct": price_vs_ema200,
                        "company_name": item.company_name,
                        "sector": item.sector,
                        "industry": item.industry,
                        "last_checked": now,
                    }
                )
                updated_items.append(updated_item)
                item_changed = True
            if item_changed:
                watchlists[wl_idx] = watchlist.model_copy(update={"items": updated_items, "updated_at": now})
                changed = True
        if changed:
            self._save_watchlists(watchlists)

    def refresh_watchlist_metrics(self, watchlist_id: str) -> Watchlist:
        rows = self._read_watchlists()
        target = next((row for row in rows if row.id == watchlist_id), None)
        if target is None:
            raise FileNotFoundError(watchlist_id)

        for item in target.items:
            try:
                scan = self.scanner_engine.scan(
                    ScannerRequest(
                        market=item.market,
                        duration="1y",
                        category="trend_mode",
                        max_results=20,
                        universe_scope="watchlist",
                        symbol_overrides=[item.symbol],
                        use_custom_rules=False,
                    )
                )
                row = scan.results[0] if scan.results else None
                score = row.current_score if row else 0.0
                dynamics = row.score_dynamics_state if row else "stable"
                self._refresh_watchlist_metrics_for_symbol(
                    item.symbol,
                    item.market,
                    current_score=score,
                    score_dynamics_state=dynamics,
                )
            except Exception:
                continue
        refreshed = self._read_watchlists()
        for row in refreshed:
            if row.id == watchlist_id:
                return row
        raise FileNotFoundError(watchlist_id)
