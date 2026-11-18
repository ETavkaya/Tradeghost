from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from tradeghost.shared.market import normalize_symbol
from tradeghost.shared.models.schemas import (
    ScannerCategory,
    StrategyLabAvoidedObservation,
    StrategyLabDecision,
    StrategyLabDecisionCreateRequest,
    StrategyLabDecisionStatus,
    StrategyLabExperiment,
    StrategyLabExperimentCreateRequest,
    StrategyLabExperimentDetail,
    StrategyLabExperimentStatus,
    StrategyLabLedgerEvent,
    StrategyLabLedgerEventType,
    StrategyLabPosition,
    StrategyLabPositionStatus,
    StrategyLabProcessResponse,
    StrategyLabSleeve,
    StrategyLabSleeveKey,
)

if TYPE_CHECKING:
    from tradeghost.services.intelligence.service import IntelligenceService


STRATEGY_LAB_POLICY_VERSION = "strategy_lab_v1"
INITIAL_SLEEVE_CASH = Decimal("100.00")
LONG_SLOT_ALLOCATION = Decimal("20.00")
LONG_SLEEVE_MAX_POSITIONS = 5
EXIT_SESSIONS = 56
CATEGORY_TO_SLEEVE = {
    ScannerCategory.TREND_MODE.value: StrategyLabSleeveKey.TREND,
    ScannerCategory.MOMENTUM_MODE.value: StrategyLabSleeveKey.MOMENTUM,
    ScannerCategory.BUILD_UP.value: StrategyLabSleeveKey.BREAKOUT,
    ScannerCategory.VALUE_REBUILD.value: StrategyLabSleeveKey.PULLBACK,
    ScannerCategory.OVEREXTENDED.value: StrategyLabSleeveKey.OVEREXTENDED_AVOIDED,
}


class StrategyLabService:
    def __init__(self, intelligence_service: IntelligenceService) -> None:
        self.intelligence_service = intelligence_service
        self.settings = intelligence_service.settings
        self.store = intelligence_service.research_record_store

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def _require_enabled(self) -> None:
        if not self.settings.product_v2_enabled or not self.settings.strategy_lab_enabled:
            raise RuntimeError(
                "Strategy Lab is disabled. Set PRODUCT_V2_ENABLED=true and STRATEGY_LAB_ENABLED=true "
                "before using its manual API."
            )
        if not self.store.configured:
            raise RuntimeError("DATABASE_URL is not configured; Strategy Lab requires Postgres.")

    @staticmethod
    def _hash(payload: dict[str, Any]) -> str:
        return StrategyLabService._intelligence_hash(payload)

    @staticmethod
    def _intelligence_hash(payload: dict[str, Any]) -> str:
        import hashlib
        import json

        encoded = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        return Decimal(str(value)).quantize(Decimal("0.000000000001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _sleeve_specs() -> tuple[tuple[StrategyLabSleeveKey, str, int, Decimal], ...]:
        return (
            (StrategyLabSleeveKey.TREND, "long", LONG_SLEEVE_MAX_POSITIONS, LONG_SLOT_ALLOCATION),
            (StrategyLabSleeveKey.MOMENTUM, "long", LONG_SLEEVE_MAX_POSITIONS, LONG_SLOT_ALLOCATION),
            (StrategyLabSleeveKey.BREAKOUT, "long", LONG_SLEEVE_MAX_POSITIONS, LONG_SLOT_ALLOCATION),
            (StrategyLabSleeveKey.PULLBACK, "long", LONG_SLEEVE_MAX_POSITIONS, LONG_SLOT_ALLOCATION),
            (StrategyLabSleeveKey.OVEREXTENDED_AVOIDED, "avoided_cash", 0, Decimal("0.00")),
        )

    def create_experiment(self, request: StrategyLabExperimentCreateRequest) -> StrategyLabExperimentDetail:
        self._require_enabled()
        now = self._now()
        if request.activation_at.tzinfo is None:
            raise ValueError("Strategy Lab activation_at must include a timezone.")
        activation_at = request.activation_at.astimezone(UTC)
        if activation_at < now:
            raise ValueError("Strategy Lab activation_at must be current or future; historical experiments are forbidden.")
        market = request.market.value
        status = (
            StrategyLabExperimentStatus.ACTIVE
            if activation_at <= now
            else StrategyLabExperimentStatus.SCHEDULED
        )
        versions = self.intelligence_service._research_versions()
        config = {
            "starting_cash_per_sleeve": str(INITIAL_SLEEVE_CASH),
            "long_sleeve_max_positions": LONG_SLEEVE_MAX_POSITIONS,
            "long_sleeve_allocation_per_slot": str(LONG_SLOT_ALLOCATION),
            "entry_policy": "first_canonical_bar_strictly_after_source_run_date_open_else_close",
            "exit_policy": f"canonical_bar_session_{EXIT_SESSIONS}_close",
            "overextended_policy": "cash_only_with_separate_hypothetical_avoided_observation",
            "category_to_sleeve": {key: value.value for key, value in CATEGORY_TO_SLEEVE.items()},
            "no_historical_cohort_conversion": True,
        }
        idempotency_key = ":".join(
            (
                request.name.strip().lower(),
                market,
                activation_at.isoformat(),
                STRATEGY_LAB_POLICY_VERSION,
            )
        )
        body = {
            "idempotency_key": idempotency_key,
            "name": request.name.strip(),
            "market": market,
            "currency": "USD",
            "activation_at": activation_at,
            "status": status,
            "policy_version": STRATEGY_LAB_POLICY_VERSION,
            "rule_version": versions["rule_version"],
            "feature_version": versions["feature_version"],
            "data_version": versions["data_version"],
            "config_json": config,
        }
        experiment = StrategyLabExperiment(
            id=str(uuid5(NAMESPACE_URL, f"tradeghost:strategy-lab:experiment:{idempotency_key}")),
            payload_hash=self._hash(body),
            created_at=now,
            **body,
        )
        sleeves = [
            StrategyLabSleeve(
                id=str(uuid5(NAMESPACE_URL, f"tradeghost:strategy-lab:sleeve:{experiment.id}:{sleeve_key.value}")),
                experiment_id=experiment.id,
                sleeve_key=sleeve_key,
                sleeve_type=sleeve_type,
                initial_cash=INITIAL_SLEEVE_CASH,
                max_positions=max_positions,
                allocation_per_slot=allocation,
                created_at=now,
            )
            for sleeve_key, sleeve_type, max_positions, allocation in self._sleeve_specs()
        ]
        initial_events = [
            self._ledger_event(
                experiment_id=experiment.id,
                sleeve_id=sleeve.id,
                event_type=StrategyLabLedgerEventType.INITIAL_CASH,
                event_date=activation_at.date(),
                data_version=experiment.data_version,
                cash_delta=INITIAL_SLEEVE_CASH,
                details={"policy_version": STRATEGY_LAB_POLICY_VERSION, "sleeve_key": sleeve.sleeve_key.value},
                idempotency_key=f"{experiment.id}:{sleeve.id}:initial_cash",
                now=now,
            )
            for sleeve in sleeves
        ]
        persisted, _, _ = self.store.create_strategy_lab_experiment(experiment, sleeves, initial_events)
        return self.get_experiment_detail(persisted.id)

    def activate_experiment(self, experiment_id: str) -> StrategyLabExperimentDetail:
        self._require_enabled()
        self.store.activate_strategy_lab_experiment(experiment_id)
        return self.get_experiment_detail(experiment_id)

    def list_experiments(self, limit: int = 30) -> list[StrategyLabExperiment]:
        self._require_enabled()
        return self.store.list_strategy_lab_experiments(limit=limit)

    def get_experiment_detail(self, experiment_id: str) -> StrategyLabExperimentDetail:
        self._require_enabled()
        experiment = self.store.get_strategy_lab_experiment(experiment_id)
        if experiment is None:
            raise FileNotFoundError(f"Strategy Lab experiment was not found: {experiment_id}")
        sleeves = self.store.list_strategy_lab_sleeves(experiment_id)
        decisions = self.store.list_strategy_lab_decisions(experiment_id)
        positions = self.store.list_strategy_lab_positions(experiment_id)
        avoided = self.store.list_strategy_lab_avoided_observations(experiment_id)
        events = self.store.list_strategy_lab_ledger_events(experiment_id)
        return StrategyLabExperimentDetail(
            experiment=experiment,
            sleeves=sleeves,
            decisions=decisions,
            positions=positions,
            avoided_observations=avoided,
            metrics=self._metrics(sleeves, decisions, positions, avoided, events),
        )

    def record_decision(
        self,
        experiment_id: str,
        request: StrategyLabDecisionCreateRequest,
    ) -> StrategyLabDecision:
        self._require_enabled()
        experiment = self.store.get_strategy_lab_experiment(experiment_id)
        if experiment is None:
            raise FileNotFoundError(f"Strategy Lab experiment was not found: {experiment_id}")
        if experiment.status != StrategyLabExperimentStatus.ACTIVE:
            raise ValueError("Strategy Lab experiment must be explicitly active before it can record decisions.")
        run = self.intelligence_service._get_run_detail(request.source_run_id)
        if run.run.timestamp < experiment.activation_at:
            raise ValueError("Historical daily-run evidence predates this experiment activation and cannot become a Strategy Lab decision.")
        symbol = normalize_symbol(request.symbol, experiment.market).strip().upper()
        candidate = next(
            (row for row in run.symbol_results if normalize_symbol(row.symbol, experiment.market).strip().upper() == symbol),
            None,
        )
        if candidate is None:
            raise ValueError(f"Symbol {symbol} is not present in the frozen source run {request.source_run_id}.")
        if candidate.market.value != experiment.market:
            raise ValueError("Source run market does not match the experiment market.")
        category = request.category.value
        category_tags = {item.value if hasattr(item, "value") else str(item) for item in candidate.category_tags}
        final_entry_decision = bool(
            candidate.structure_snapshot.get("final_entry_decision")
            if isinstance(candidate.structure_snapshot, dict)
            else False
        )
        source_candidate = {
            "run": run.run.model_dump(mode="json"),
            "candidate": candidate.model_dump(mode="json"),
            "selected_category": category,
        }
        source_hash = self._hash(source_candidate)
        sleeves = {sleeve.sleeve_key: sleeve for sleeve in self.store.list_strategy_lab_sleeves(experiment_id)}
        sleeve_key = CATEGORY_TO_SLEEVE[category]
        sleeve = sleeves[sleeve_key]
        reasons: list[str] = []
        position: StrategyLabPosition | None = None
        events: list[StrategyLabLedgerEvent] = []
        avoided: StrategyLabAvoidedObservation | None = None
        now = self._now()
        if category not in category_tags:
            reasons.append("category_not_present_in_frozen_source_run")
            status = StrategyLabDecisionStatus.REJECTED
            sleeve_id = None
        elif sleeve_key == StrategyLabSleeveKey.OVEREXTENDED_AVOIDED:
            reasons.append("overextended_sleeve_cash_policy")
            status = StrategyLabDecisionStatus.AVOIDED
            sleeve_id = sleeve.id
        elif not final_entry_decision:
            reasons.append("final_entry_decision_false")
            status = StrategyLabDecisionStatus.REJECTED
            sleeve_id = sleeve.id
        elif candidate.data_quality_flags:
            reasons.append("source_data_quality_flags")
            status = StrategyLabDecisionStatus.REJECTED
            sleeve_id = sleeve.id
        else:
            positions = self.store.list_strategy_lab_positions(experiment_id)
            active_positions = [
                row for row in positions if row.status in {StrategyLabPositionStatus.PENDING_ENTRY, StrategyLabPositionStatus.OPEN}
            ]
            if any(row.symbol == symbol for row in active_positions):
                reasons.append("duplicate_open_exposure")
                status = StrategyLabDecisionStatus.REJECTED
                sleeve_id = sleeve.id
            elif sum(1 for row in active_positions if row.sleeve_id == sleeve.id) >= sleeve.max_positions:
                reasons.append("sleeve_capacity_reached")
                status = StrategyLabDecisionStatus.REJECTED
                sleeve_id = sleeve.id
            else:
                reasons.append("deterministic_final_entry_eligible")
                status = StrategyLabDecisionStatus.RESERVED
                sleeve_id = sleeve.id
        idempotency_key = f"{experiment_id}:{request.source_run_id}:{symbol}:{category}"
        decision_id = str(uuid5(NAMESPACE_URL, f"tradeghost:strategy-lab:decision:{idempotency_key}"))
        if status == StrategyLabDecisionStatus.RESERVED:
            position_id = str(uuid5(NAMESPACE_URL, f"tradeghost:strategy-lab:position:{decision_id}"))
            position = StrategyLabPosition(
                id=position_id,
                experiment_id=experiment_id,
                sleeve_id=sleeve.id,
                decision_id=decision_id,
                symbol=symbol,
                market=experiment.market,
                status=StrategyLabPositionStatus.PENDING_ENTRY,
                allocated_cash=sleeve.allocation_per_slot,
                scheduled_exit_sessions=EXIT_SESSIONS,
                created_at=now,
                updated_at=now,
            )
            events.append(
                self._ledger_event(
                    experiment_id=experiment_id,
                    sleeve_id=sleeve.id,
                    position_id=position_id,
                    decision_id=decision_id,
                    event_type=StrategyLabLedgerEventType.ENTRY_RESERVED,
                    event_date=run.run.date,
                    data_version=experiment.data_version,
                    cash_delta=Decimal("0"),
                    details={"allocated_cash": str(sleeve.allocation_per_slot), "source_run_id": run.run.id},
                    idempotency_key=f"{decision_id}:entry_reserved",
                    now=now,
                )
            )
        elif status == StrategyLabDecisionStatus.AVOIDED:
            avoided = StrategyLabAvoidedObservation(
                id=str(uuid5(NAMESPACE_URL, f"tradeghost:strategy-lab:avoided:{decision_id}")),
                idempotency_key=f"{decision_id}:avoided",
                experiment_id=experiment_id,
                decision_id=decision_id,
                symbol=symbol,
                market=experiment.market,
                source_run_date=run.run.date,
                planned_allocation=LONG_SLOT_ALLOCATION,
                status="pending_entry_price",
                data_version=experiment.data_version,
                details_json={"policy": "overextended_cash_only", "source_run_id": run.run.id},
                created_at=now,
                updated_at=now,
            )
        versions = self.intelligence_service._research_versions()
        body = {
            "idempotency_key": idempotency_key,
            "experiment_id": experiment_id,
            "sleeve_id": sleeve_id,
            "source_run_id": run.run.id,
            "source_run_at": run.run.timestamp,
            "source_run_date": run.run.date,
            "symbol": symbol,
            "market": experiment.market,
            "category": category,
            "decision_status": status,
            "reason_codes": reasons,
            "final_entry_decision": final_entry_decision,
            "source_candidate_hash": source_hash,
            "source_candidate_json": source_candidate,
            "rule_version": versions["rule_version"],
            "feature_version": versions["feature_version"],
            "data_version": experiment.data_version,
        }
        decision = StrategyLabDecision(
            id=decision_id,
            payload_hash=self._hash(body),
            position_id=position.id if position else None,
            created_at=now,
            **body,
        )
        persisted, _ = self.store.create_strategy_lab_decision(
            decision,
            position=position,
            ledger_events=events,
            avoided_observation=avoided,
        )
        return persisted

    def process_experiment(self, experiment_id: str, *, as_of_date: date | None = None) -> StrategyLabProcessResponse:
        self._require_enabled()
        experiment = self.store.get_strategy_lab_experiment(experiment_id)
        if experiment is None:
            raise FileNotFoundError(f"Strategy Lab experiment was not found: {experiment_id}")
        if experiment.status != StrategyLabExperimentStatus.ACTIVE:
            raise ValueError("Strategy Lab experiment must be active before manual processing.")
        through_date = as_of_date or date.today()
        if through_date > date.today():
            raise ValueError("Strategy Lab processing cannot use a future as_of_date.")
        response = StrategyLabProcessResponse(experiment_id=experiment_id, as_of_date=through_date)
        decisions = {decision.id: decision for decision in self.store.list_strategy_lab_decisions(experiment_id)}
        for position in self.store.list_strategy_lab_positions(experiment_id):
            decision = decisions[position.decision_id]
            bars, data_version, flags = self.intelligence_service._load_canonical_bars_for_symbol(
                position.symbol,
                market=position.market,
                as_of_date=through_date,
                base_data_version=experiment.data_version,
            )
            if flags:
                self._record_quality_hold(experiment, position, decision, through_date, data_version, flags)
                held = position.model_copy(update={"status": StrategyLabPositionStatus.DATA_QUALITY_HOLD, "updated_at": self._now()})
                self.store.update_strategy_lab_position(held)
                response.data_quality_holds += 1
                continue
            if position.status == StrategyLabPositionStatus.PENDING_ENTRY:
                entry_bar = next((bar for bar in bars if bar["bar_date"] > decision.source_run_date), None)
                if entry_bar is None:
                    continue
                entry_price = self._decimal(entry_bar.get("open") or entry_bar["close"])
                if entry_price <= 0:
                    self._record_quality_hold(experiment, position, decision, through_date, data_version, ["invalid_entry_price"])
                    response.data_quality_holds += 1
                    continue
                quantity = (position.allocated_cash / entry_price).quantize(Decimal("0.000000000001"), rounding=ROUND_HALF_UP)
                event, created = self.store.create_strategy_lab_ledger_event(
                    self._ledger_event(
                        experiment_id=experiment.id,
                        sleeve_id=position.sleeve_id,
                        position_id=position.id,
                        decision_id=decision.id,
                        event_type=StrategyLabLedgerEventType.ENTRY_FILL,
                        event_date=entry_bar["bar_date"],
                        data_version=data_version,
                        cash_delta=-position.allocated_cash,
                        quantity=quantity,
                        price=entry_price,
                        source_bar_date=entry_bar["bar_date"],
                        price_source="canonical_next_session_open_or_close_fallback",
                        details={"source_run_date": decision.source_run_date.isoformat()},
                        idempotency_key=f"{position.id}:entry_fill:{entry_bar['bar_date'].isoformat()}:{data_version}",
                        now=self._now(),
                    )
                )
                filled = position.model_copy(
                    update={
                        "status": StrategyLabPositionStatus.OPEN,
                        "quantity": quantity,
                        "entry_date": entry_bar["bar_date"],
                        "entry_price": entry_price,
                        "entry_data_version": data_version,
                        "updated_at": self._now(),
                    }
                )
                position = self.store.update_strategy_lab_position(filled)
                response.entry_fills_created += int(created)
            if position.status != StrategyLabPositionStatus.OPEN or position.entry_date is None or position.quantity is None:
                continue
            entry_index = next((index for index, bar in enumerate(bars) if bar["bar_date"] == position.entry_date), None)
            if entry_index is None:
                self._record_quality_hold(experiment, position, decision, through_date, data_version, ["missing_entry_bar"])
                response.data_quality_holds += 1
                continue
            exit_index = entry_index + (position.scheduled_exit_sessions - 1)
            if len(bars) > exit_index:
                exit_bar = bars[exit_index]
                exit_price = self._decimal(exit_bar["close"])
                proceeds = (position.quantity * exit_price).quantize(Decimal("0.000000000001"), rounding=ROUND_HALF_UP)
                _, created = self.store.create_strategy_lab_ledger_event(
                    self._ledger_event(
                        experiment_id=experiment.id,
                        sleeve_id=position.sleeve_id,
                        position_id=position.id,
                        decision_id=decision.id,
                        event_type=StrategyLabLedgerEventType.EXIT_FILL,
                        event_date=exit_bar["bar_date"],
                        data_version=data_version,
                        cash_delta=proceeds,
                        quantity=position.quantity,
                        price=exit_price,
                        source_bar_date=exit_bar["bar_date"],
                        price_source="canonical_session_56_close",
                        details={"scheduled_exit_sessions": position.scheduled_exit_sessions},
                        idempotency_key=f"{position.id}:exit_fill:{exit_bar['bar_date'].isoformat()}:{data_version}",
                        now=self._now(),
                    )
                )
                closed = position.model_copy(
                    update={
                        "status": StrategyLabPositionStatus.CLOSED,
                        "exit_date": exit_bar["bar_date"],
                        "exit_price": exit_price,
                        "exit_data_version": data_version,
                        "realised_pnl": proceeds - position.allocated_cash,
                        "latest_valuation_date": exit_bar["bar_date"],
                        "latest_valuation_price": exit_price,
                        "updated_at": self._now(),
                    }
                )
                self.store.update_strategy_lab_position(closed)
                response.exits_created += int(created)
            else:
                valuation_bar = bars[-1]
                valuation_price = self._decimal(valuation_bar["close"])
                _, created = self.store.create_strategy_lab_ledger_event(
                    self._ledger_event(
                        experiment_id=experiment.id,
                        sleeve_id=position.sleeve_id,
                        position_id=position.id,
                        decision_id=decision.id,
                        event_type=StrategyLabLedgerEventType.VALUATION,
                        event_date=valuation_bar["bar_date"],
                        data_version=data_version,
                        quantity=position.quantity,
                        price=valuation_price,
                        source_bar_date=valuation_bar["bar_date"],
                        price_source="canonical_close",
                        details={"unrealised_pnl": str((position.quantity * valuation_price) - position.allocated_cash)},
                        idempotency_key=f"{position.id}:valuation:{valuation_bar['bar_date'].isoformat()}:{data_version}",
                        now=self._now(),
                    )
                )
                valued = position.model_copy(
                    update={
                        "latest_valuation_date": valuation_bar["bar_date"],
                        "latest_valuation_price": valuation_price,
                        "updated_at": self._now(),
                    }
                )
                self.store.update_strategy_lab_position(valued)
                response.valuations_created += int(created)
        response.avoided_updates = self._process_avoided(experiment, through_date)
        return response

    def _process_avoided(self, experiment: StrategyLabExperiment, through_date: date) -> int:
        updates = 0
        for observation in self.store.list_strategy_lab_avoided_observations(experiment.id):
            bars, data_version, flags = self.intelligence_service._load_canonical_bars_for_symbol(
                observation.symbol,
                market=observation.market,
                as_of_date=through_date,
                base_data_version=experiment.data_version,
            )
            if flags:
                continue
            entry_date = observation.entry_date
            entry_price = observation.entry_price
            if entry_date is None:
                entry_bar = next((bar for bar in bars if bar["bar_date"] > observation.source_run_date), None)
                if entry_bar is None:
                    continue
                entry_date = entry_bar["bar_date"]
                entry_price = self._decimal(entry_bar.get("open") or entry_bar["close"])
            entry_index = next((index for index, bar in enumerate(bars) if bar["bar_date"] == entry_date), None)
            if entry_index is None or entry_price is None:
                continue
            exit_index = entry_index + (EXIT_SESSIONS - 1)
            update = {"entry_date": entry_date, "entry_price": entry_price, "data_version": data_version, "updated_at": self._now()}
            if len(bars) > exit_index:
                exit_bar = bars[exit_index]
                exit_price = self._decimal(exit_bar["close"])
                update.update(
                    {
                        "status": "complete",
                        "exit_date": exit_bar["bar_date"],
                        "exit_price": exit_price,
                        "return_pct": ((exit_price - entry_price) / entry_price * Decimal("100")),
                    }
                )
            else:
                update["status"] = "tracking"
            self.store.update_strategy_lab_avoided_observation(observation.model_copy(update=update))
            updates += 1
        return updates

    def _record_quality_hold(
        self,
        experiment: StrategyLabExperiment,
        position: StrategyLabPosition,
        decision: StrategyLabDecision,
        as_of_date: date,
        data_version: str,
        flags: list[str],
    ) -> None:
        self.store.create_strategy_lab_ledger_event(
            self._ledger_event(
                experiment_id=experiment.id,
                sleeve_id=position.sleeve_id,
                position_id=position.id,
                decision_id=decision.id,
                event_type=StrategyLabLedgerEventType.DATA_QUALITY_EXCEPTION,
                event_date=as_of_date,
                data_version=data_version,
                details={"flags": sorted(set(flags))},
                idempotency_key=f"{position.id}:quality:{as_of_date.isoformat()}:{self._hash({'flags': sorted(set(flags)), 'data_version': data_version})[:12]}",
                now=self._now(),
            )
        )

    def _ledger_event(
        self,
        *,
        experiment_id: str,
        event_type: StrategyLabLedgerEventType,
        event_date: date,
        data_version: str,
        idempotency_key: str,
        now: datetime,
        sleeve_id: str | None = None,
        position_id: str | None = None,
        decision_id: str | None = None,
        cash_delta: Decimal = Decimal("0"),
        quantity: Decimal | None = None,
        price: Decimal | None = None,
        source_bar_date: date | None = None,
        price_source: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> StrategyLabLedgerEvent:
        return StrategyLabLedgerEvent(
            id=str(uuid5(NAMESPACE_URL, f"tradeghost:strategy-lab:ledger:{idempotency_key}")),
            idempotency_key=idempotency_key,
            experiment_id=experiment_id,
            sleeve_id=sleeve_id,
            position_id=position_id,
            decision_id=decision_id,
            event_type=event_type,
            event_date=event_date,
            cash_delta=cash_delta,
            quantity=quantity,
            price=price,
            source_bar_date=source_bar_date,
            price_source=price_source,
            data_version=data_version,
            details_json=details or {},
            created_at=now,
        )

    @staticmethod
    def _metrics(
        sleeves: list[StrategyLabSleeve],
        decisions: list[StrategyLabDecision],
        positions: list[StrategyLabPosition],
        avoided: list[StrategyLabAvoidedObservation],
        events: list[StrategyLabLedgerEvent],
    ) -> dict[str, Any]:
        cash_by_sleeve = {sleeve.id: Decimal("0") for sleeve in sleeves}
        for event in events:
            if event.sleeve_id in cash_by_sleeve:
                cash_by_sleeve[event.sleeve_id] += event.cash_delta
        open_value_by_sleeve = Counter()
        for position in positions:
            if position.status == StrategyLabPositionStatus.OPEN and position.quantity and position.latest_valuation_price:
                open_value_by_sleeve[position.sleeve_id] += position.quantity * position.latest_valuation_price
        realised = [position.realised_pnl for position in positions if position.realised_pnl is not None]
        wins = [value for value in realised if value > 0]
        losses = [value for value in realised if value < 0]
        cash_for_drawdown = Counter()
        value_for_drawdown = Counter()
        peak_value = Decimal("0")
        max_drawdown_pct = Decimal("0")
        for event in sorted(events, key=lambda row: (row.event_date, row.created_at, row.id)):
            if event.sleeve_id:
                cash_for_drawdown[event.sleeve_id] += event.cash_delta
            if event.position_id and event.event_type in {
                StrategyLabLedgerEventType.ENTRY_FILL,
                StrategyLabLedgerEventType.VALUATION,
            } and event.quantity is not None and event.price is not None:
                value_for_drawdown[event.position_id] = event.quantity * event.price
            elif event.position_id and event.event_type == StrategyLabLedgerEventType.EXIT_FILL:
                value_for_drawdown[event.position_id] = Decimal("0")
            equity_value = sum(cash_for_drawdown.values(), Decimal("0")) + sum(value_for_drawdown.values(), Decimal("0"))
            peak_value = max(peak_value, equity_value)
            if peak_value > 0:
                max_drawdown_pct = max(max_drawdown_pct, ((peak_value - equity_value) / peak_value) * Decimal("100"))
        rejected = Counter(reason for decision in decisions if decision.decision_status == StrategyLabDecisionStatus.REJECTED for reason in decision.reason_codes)
        hold_count = sum(1 for position in positions if position.status == StrategyLabPositionStatus.DATA_QUALITY_HOLD)
        sleeve_metrics = {}
        for sleeve in sleeves:
            active = sum(1 for position in positions if position.sleeve_id == sleeve.id and position.status in {StrategyLabPositionStatus.PENDING_ENTRY, StrategyLabPositionStatus.OPEN})
            sleeve_metrics[sleeve.sleeve_key.value] = {
                "cash": str(cash_by_sleeve[sleeve.id]),
                "open_value": str(open_value_by_sleeve[sleeve.id]),
                "active_positions": active,
                "max_positions": sleeve.max_positions,
                "capacity_used_pct": round((active / sleeve.max_positions * 100.0), 2) if sleeve.max_positions else 0.0,
            }
        avoided_complete = [item for item in avoided if item.return_pct is not None]
        holding_days = [
            (position.exit_date - position.entry_date).days
            for position in positions
            if position.entry_date is not None and position.exit_date is not None
        ]
        return {
            "sleeves": sleeve_metrics,
            "realised_pnl": str(sum(realised, Decimal("0"))),
            "hit_rate_pct": round((len(wins) / len(realised) * 100.0), 2) if realised else None,
            "average_win": str(sum(wins, Decimal("0")) / len(wins)) if wins else None,
            "average_loss": str(sum(losses, Decimal("0")) / len(losses)) if losses else None,
            "max_drawdown_pct": str(max_drawdown_pct.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
            "holding_period_days": {
                "count": len(holding_days),
                "average": round(sum(holding_days) / len(holding_days), 2) if holding_days else None,
                "minimum": min(holding_days) if holding_days else None,
                "maximum": max(holding_days) if holding_days else None,
            },
            "rejected_reason_counts": dict(sorted(rejected.items())),
            "data_quality_hold_count": hold_count,
            "avoided_basket": {
                "count": len(avoided),
                "complete_count": len(avoided_complete),
                "average_return_pct": str(sum((item.return_pct for item in avoided_complete), Decimal("0")) / len(avoided_complete)) if avoided_complete else None,
                "excluded_from_realised_pnl": True,
            },
            "drawdown_basis": "append-only cash and canonical mark-to-market ledger events; avoided observations excluded",
        }
