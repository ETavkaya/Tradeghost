from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from tradeghost.services.analysis_engine import AnalysisEngine
from tradeghost.services.scanner.engine import ScannerEngine
from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.models.schemas import (
    AlertEvent,
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
    Watchlist,
    WatchlistCreateRequest,
    WatchlistItem,
    WatchlistItemCreateRequest,
    WatchlistRenameRequest,
)


class MonitoringService:
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
                combined = self.analysis_engine.analyze_combined(
                    ticker=symbol,
                    market=req.market.value,
                    window="1y",
                    strategy_mode="balanced",
                )
                added_price = float(combined.indicator_summary.get("close", 0.0)) or None
                added_price_estimated = added_price is not None
            except Exception:
                added_price = None
                added_price_estimated = False

            item = WatchlistItem(
                watchlist_id=row.id,
                symbol=symbol,
                market=req.market,
                added_at=datetime.now(UTC),
                notes=req.notes,
                added_price=added_price,
                added_price_estimated=added_price_estimated,
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
            scanner_context=scanner_context,
            analysis_context=analysis_context,
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
                    analysis_context={"trend_state": setup.trend_state},
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
                    analysis_context={"trend_state": setup.trend_state},
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
                    analysis_context={"trend_state": setup.trend_state},
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
                    analysis_context={"trend_state": setup.trend_state},
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
                    analysis_context={"trend_state": setup.trend_state},
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
                    analysis_context={"trend_state": setup.trend_state},
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
                    analysis_context={"trend_state": setup.trend_state},
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
                    analysis_context={"trend_state": setup.trend_state},
                )
        elif rule.rule_type == AlertRuleType.PRICE_GTE and value is not None and close >= value:
            return self._build_alert_event(
                rule=rule,
                symbol=symbol,
                triggered_value=close,
                message=f"{symbol} price {close:.2f} >= {value:.2f}",
                trigger_context={"price": close, "threshold": value},
                scanner_context={},
                analysis_context={"trend_state": setup.trend_state},
            )
        elif rule.rule_type == AlertRuleType.PRICE_LTE and value is not None and close <= value:
            return self._build_alert_event(
                rule=rule,
                symbol=symbol,
                triggered_value=close,
                message=f"{symbol} price {close:.2f} <= {value:.2f}",
                trigger_context={"price": close, "threshold": value},
                scanner_context={},
                analysis_context={"trend_state": setup.trend_state},
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
                    analysis_context={"trend_state": setup.trend_state},
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
                    analysis_context={"trend_state": setup.trend_state},
                )
        elif rule.rule_type == AlertRuleType.VOLUME_RATIO_20_GTE and value is not None and vol_ratio >= value:
            return self._build_alert_event(
                rule=rule,
                symbol=symbol,
                triggered_value=round(vol_ratio, 2),
                message=f"{symbol} volume ratio 20 {vol_ratio:.2f} >= {value:.2f}",
                trigger_context={"volume_ratio_20": round(vol_ratio, 2), "threshold": value},
                scanner_context={},
                analysis_context={"trend_state": setup.trend_state},
            )
        elif rule.rule_type == AlertRuleType.RSI14_LTE and value is not None and rsi14 <= value:
            return self._build_alert_event(
                rule=rule,
                symbol=symbol,
                triggered_value=round(rsi14, 2),
                message=f"{symbol} RSI14 {rsi14:.2f} <= {value:.2f}",
                trigger_context={"rsi_14": round(rsi14, 2), "threshold": value},
                scanner_context={},
                analysis_context={"trend_state": setup.trend_state},
            )
        elif rule.rule_type == AlertRuleType.RSI14_GTE and value is not None and rsi14 >= value:
            return self._build_alert_event(
                rule=rule,
                symbol=symbol,
                triggered_value=round(rsi14, 2),
                message=f"{symbol} RSI14 {rsi14:.2f} >= {value:.2f}",
                trigger_context={"rsi_14": round(rsi14, 2), "threshold": value},
                scanner_context={},
                analysis_context={"trend_state": setup.trend_state},
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
                    analysis_context={"trend_state": setup.trend_state},
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
                    analysis_context={"trend_state": row.trend_state},
                )
            )
        return events

    def run_monitoring(self, req: MonitoringRunRequest) -> MonitoringRunSummary:
        started = datetime.now(UTC)
        started_monotonic = time.monotonic()
        rules = [rule for rule in self._read_rules() if rule.is_enabled]
        events = self._read_events()
        rules_all = self._read_rules()
        rules_index = {row.id: row for row in rules_all}
        created: list[AlertEvent] = []
        processed_rules = 0
        evaluated_symbols = 0
        partial = False
        note = None

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
                    created.extend(scanner_events)
                    matched_for_rule = len(scanner_events) > 0
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
                        created.append(
                            self._build_alert_event(
                                rule=rule,
                                symbol=row.symbol,
                                triggered_value=row.score_dynamics_state,
                                message=f"{row.symbol} score dynamics became {row.score_dynamics_state}",
                                trigger_context={"state": row.score_dynamics_state},
                                scanner_context={"scanner_score": row.scanner_score},
                                analysis_context={"trend_state": row.trend_state},
                            )
                        )
                        matched_for_rule = True
                evaluated_symbols += len(symbols)
                rule_payload = rules_index.get(rule.id).model_dump() if rules_index.get(rule.id) else rule.model_dump()
                now_checked = datetime.now(UTC)
                rule_payload["last_checked"] = now_checked
                if matched_for_rule:
                    rule_payload["last_matched"] = now_checked
                rules_index[rule.id] = AlertRule.model_validate(rule_payload)
                continue

            for symbol in symbols:
                event = self._evaluate_symbol_rule(rule, symbol)
                evaluated_symbols += 1
                if event is not None:
                    created.append(event)
                    matched_for_rule = True
                try:
                    scan = self.scanner_engine.scan(
                        ScannerRequest(
                            market=rule.market,
                            duration="1y",
                            category="trend_mode",
                            max_results=20,
                            universe_scope="watchlist",
                            symbol_overrides=[symbol],
                            use_custom_rules=False,
                        )
                    )
                    row = scan.results[0] if scan.results else None
                    if row is not None:
                        self._refresh_watchlist_metrics_for_symbol(
                            symbol,
                            rule.market,
                            current_score=row.current_score,
                            score_dynamics_state=row.score_dynamics_state,
                        )
                except Exception:
                    continue

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
        return MonitoringRunSummary(
            started_at=started,
            finished_at=finished,
            processed_rules=processed_rules,
            evaluated_symbols=evaluated_symbols,
            events_created=len(created),
            partial_run=partial,
            note=note,
        )

    def run_due_schedules(self, max_runtime_seconds: float = 30.0) -> MonitoringRunSummary:
        self._ensure_default_schedule()
        schedules = [
            row
            for row in self._read_schedules()
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
        aggregate.finished_at = datetime.now(UTC)
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

        chart_candles = combined.chart.candles
        closes = [float(c.close) for c in chart_candles]
        current_price = closes[-1] if closes else float(combined.indicator_summary.get("close", 0.0))
        price_vs_ema200 = combined.regime.price_vs_ema200_pct

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
                    estimated = self._nearest_close_to_datetime(chart_candles, item.added_at)
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
