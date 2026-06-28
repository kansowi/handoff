from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from app.handoff_packet import build_handoff_packet
from app.models import (
    AuditExport,
    AutonomyBlueprint,
    BlueprintRecord,
    CompileTraceStep,
    ControlContract,
    ControlSummary,
    EvalCheck,
    EvalSummary,
    LearningUpdate,
    RunEvent,
    RunRecord,
    SimulationResponse,
    SimulationRun,
)


DEFAULT_DB_PATH = ".data/handoff.sqlite3"


class HandoffRepository:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or os.getenv("HANDOFF_DB_PATH", DEFAULT_DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def source_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def save_blueprint(
        self,
        *,
        source_text: str,
        blueprint: AutonomyBlueprint,
        contracts: list[ControlContract],
        compile_trace: list[CompileTraceStep],
        control_summary: ControlSummary,
    ) -> str:
        blueprint_id = f"bp_{uuid4().hex[:12]}"
        created_at = _now()
        with self._connect() as conn:
            conn.execute(
                """
                insert into blueprints (
                    blueprint_id, source_hash, source_text, blueprint_json,
                    contracts_json, compile_trace_json, control_summary_json, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    blueprint_id,
                    self.source_hash(source_text),
                    source_text,
                    _dump(blueprint),
                    _dump_list(contracts),
                    _dump_list(compile_trace),
                    _dump(control_summary),
                    created_at,
                ),
            )
        return blueprint_id

    def get_blueprint(self, blueprint_id: str) -> BlueprintRecord | None:
        with self._connect() as conn:
            row = conn.execute("select * from blueprints where blueprint_id = ?", (blueprint_id,)).fetchone()
            if row is None:
                return None
            latest = conn.execute(
                "select run_id, status from runs where blueprint_id = ? order by started_at desc limit 1",
                (blueprint_id,),
            ).fetchone()
        blueprint = AutonomyBlueprint.model_validate_json(row["blueprint_json"])
        contracts = _load_list(row["contracts_json"], ControlContract)
        control_summary = ControlSummary.model_validate_json(row["control_summary_json"])
        return BlueprintRecord(
            blueprint_id=row["blueprint_id"],
            source_hash=row["source_hash"],
            blueprint=blueprint,
            contracts=contracts,
            compile_trace=_load_list(row["compile_trace_json"], CompileTraceStep),
            control_summary=control_summary,
            handoff_packet=build_handoff_packet(blueprint, contracts, control_summary),
            created_at=row["created_at"],
            latest_run_id=latest["run_id"] if latest else None,
            latest_run_status=latest["status"] if latest else None,
        )

    def save_run(self, simulation: SimulationResponse) -> None:
        now = _now()
        run = SimulationRun(
            run_id=simulation.run_id,
            blueprint_id=simulation.blueprint_id,
            case_id=simulation.case.case_id,
            status=simulation.status,
            started_at=simulation.events[0].timestamp if simulation.events else now,
            completed_at=simulation.events[-1].timestamp if simulation.events else now,
        )
        with self._connect() as conn:
            conn.execute(
                """
                insert into runs (
                    run_id, blueprint_id, case_json, run_json, contracts_json, eval_summary_json, status, started_at, completed_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    simulation.run_id,
                    simulation.blueprint_id,
                    _dump(simulation.case),
                    _dump(run),
                    _dump_list(simulation.contracts),
                    _dump(simulation.eval_summary),
                    simulation.status,
                    run.started_at,
                    run.completed_at,
                ),
            )
            for event in simulation.events:
                conn.execute(
                    "insert into run_events (run_id, sequence, event_id, event_json) values (?, ?, ?, ?)",
                    (simulation.run_id, event.sequence, event.event_id, _dump(event)),
                )
            for check in simulation.eval_summary.checks:
                conn.execute(
                    "insert into eval_results (run_id, check_id, eval_json) values (?, ?, ?)",
                    (simulation.run_id, check.check_id, _dump(check)),
                )
            for update in simulation.learning_updates:
                conn.execute(
                    "insert into learning_updates (run_id, update_id, update_json) values (?, ?, ?)",
                    (simulation.run_id, update.update_id, _dump(update)),
                )

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as conn:
            run_row = conn.execute("select * from runs where run_id = ?", (run_id,)).fetchone()
            if run_row is None:
                return None
            event_rows = conn.execute(
                "select event_json from run_events where run_id = ? order by sequence asc",
                (run_id,),
            ).fetchall()
            eval_rows = conn.execute("select eval_json from eval_results where run_id = ?", (run_id,)).fetchall()
            learning_rows = conn.execute(
                "select update_json from learning_updates where run_id = ? order by update_id asc",
                (run_id,),
            ).fetchall()

        checks = [EvalCheck.model_validate_json(row["eval_json"]) for row in eval_rows]
        return RunRecord(
            run=SimulationRun.model_validate_json(run_row["run_json"]),
            case=json_model(run_row["case_json"]),
            events=[RunEvent.model_validate_json(row["event_json"]) for row in event_rows],
            eval_summary=EvalSummary(
                checks=checks,
                pass_count=sum(1 for check in checks if check.status == "pass"),
                warn_count=sum(1 for check in checks if check.status == "warn"),
                fail_count=sum(1 for check in checks if check.status == "fail"),
            ),
            learning_updates=[LearningUpdate.model_validate_json(row["update_json"]) for row in learning_rows],
            contracts=_load_list(run_row["contracts_json"], ControlContract),
        )

    def build_audit_export(self, run_id: str, runtime_metadata: dict) -> AuditExport | None:
        run_record = self.get_run(run_id)
        if run_record is None:
            return None
        blueprint_record = self.get_blueprint(run_record.run.blueprint_id)
        if blueprint_record is None:
            return None
        return AuditExport(
            run=run_record.run,
            case=run_record.case,
            blueprint=blueprint_record.blueprint,
            contracts=run_record.contracts,
            events=run_record.events,
            eval_summary=run_record.eval_summary,
            learning_updates=run_record.learning_updates,
            runtime_metadata=runtime_metadata,
        )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        conn.execute("pragma journal_mode = wal")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                create table if not exists blueprints (
                    blueprint_id text primary key,
                    source_hash text not null,
                    source_text text not null,
                    blueprint_json text not null,
                    contracts_json text not null,
                    compile_trace_json text not null,
                    control_summary_json text not null,
                    created_at text not null
                );

                create table if not exists runs (
                    run_id text primary key,
                    blueprint_id text not null references blueprints(blueprint_id) on delete cascade,
                    case_json text not null,
                    run_json text not null,
                    contracts_json text not null,
                    eval_summary_json text not null,
                    status text not null,
                    started_at text not null,
                    completed_at text not null
                );

                create table if not exists run_events (
                    run_id text not null references runs(run_id) on delete cascade,
                    sequence integer not null,
                    event_id text not null,
                    event_json text not null,
                    primary key (run_id, sequence)
                );

                create table if not exists eval_results (
                    run_id text not null references runs(run_id) on delete cascade,
                    check_id text not null,
                    eval_json text not null,
                    primary key (run_id, check_id)
                );

                create table if not exists learning_updates (
                    run_id text not null references runs(run_id) on delete cascade,
                    update_id text not null,
                    update_json text not null,
                    primary key (run_id, update_id)
                );

                create index if not exists idx_blueprints_source_hash on blueprints(source_hash);
                create index if not exists idx_runs_blueprint on runs(blueprint_id, started_at);
                """
            )


def json_model(value: str):
    from app.models import SimulationCase

    return SimulationCase.model_validate_json(value)


def _dump(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), separators=(",", ":"))


def _dump_list(models: list[BaseModel]) -> str:
    return json.dumps([model.model_dump(mode="json") for model in models], separators=(",", ":"))


def _load_list(value: str, model_type):
    return [model_type.model_validate(item) for item in json.loads(value)]


def _now() -> str:
    return datetime.now(UTC).isoformat()
