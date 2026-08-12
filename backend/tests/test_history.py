"""Document history: persistence, the read/delete endpoints, and the failure policy.

No network and no real database. `FakeStore` below is a small in-memory stand-in
for the postgrest query builder — it actually filters, orders, projects columns and
deletes rows, so these assert on OUTCOMES rather than on which methods were called.
A recorder-only double would pass just as happily against a query that selects the
wrong columns.

The rule this module exists to pin, above all others: a storage failure must never
turn a completed analysis into a failed one, and must never turn an unreachable
database into an empty history list. Those are the two ways persistence could make
this product lie.

Run: python backend/tests/test_history.py
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone

from _harness import Results, make_text_pdf, scrub_live_credentials

import main
from config import HISTORY_PAGE_SIZE, HISTORY_RETENTION_DAYS
from models.schemas import (
    AnalysisResult,
    AnalysisRun,
    AnalyzedChunk,
    ChunkAnalysis,
    ChunkFailure,
    ChunkFailureReason,
    DocumentMeta,
    ExtractionMethod,
    JobStatus,
    MissingClause,
    PageText,
    RiskFlag,
    RiskLevel,
    SectionAnalysis,
    SkippedSection,
)
from services.aggregator import aggregate_run
from services import supabase as history
from services.supabase import (
    HistoryError,
    StaleAnalysisError,
    delete_analysis,
    get_analysis,
    list_analyses,
    save_analysis,
)
from test_pipeline import FakeClient, stub_response

from fastapi.testclient import TestClient

# Must run after `import main` — see _harness.scrub_live_credentials. Without it
# every check below would write into the developer's real Supabase project.
scrub_live_credentials()

LEAK_MARKER = "postgrest-internal-detail-do-not-leak"


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- the fake store


class FakeResponse:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class FakeQuery:
    """One postgrest-style chained query against FakeStore."""

    def __init__(self, store: "FakeStore", op: str, columns: str = "*") -> None:
        self.store = store
        self.op = op
        self.columns = columns
        self.filters: list[tuple[str, str, object]] = []
        self.order_column: str | None = None
        self.descending = False
        self.max_rows: int | None = None
        self.payload: dict | None = None

    def eq(self, column: str, value):
        self.filters.append(("eq", column, value))
        return self

    def lt(self, column: str, value):
        self.filters.append(("lt", column, value))
        return self

    def order(self, column: str, desc: bool = False):
        self.order_column = column
        self.descending = desc
        return self

    def limit(self, count: int):
        self.max_rows = count
        return self

    def _matches(self, row: dict) -> bool:
        for kind, column, value in self.filters:
            actual = row.get(column)
            if kind == "eq" and str(actual) != str(value):
                return False
            if kind == "lt":
                # created_at is stored as an ISO string, exactly as postgrest
                # returns it. Parse both sides rather than comparing strings.
                if not datetime.fromisoformat(str(actual)) < datetime.fromisoformat(
                    str(value)
                ):
                    return False
        return True

    def _project(self, row: dict) -> dict:
        if self.columns == "*":
            return dict(row)
        # KeyError on an unknown column is deliberate: a typo in _LIST_COLUMNS
        # should fail loudly here rather than silently return partial rows.
        return {name: row[name] for name in self.columns.split(",")}

    async def execute(self) -> FakeResponse:
        self.store.operations.append((self.op, self.columns))
        if self.store.fail_on and self.op in self.store.fail_on:
            raise RuntimeError(LEAK_MARKER)

        if self.op == "insert":
            row = dict(self.payload or {})
            row.setdefault("id", str(uuid.uuid4()))
            row.setdefault("created_at", datetime.now(timezone.utc).isoformat())
            self.store.rows.append(row)
            return FakeResponse([{"id": row["id"]}])

        matched = [row for row in self.store.rows if self._matches(row)]

        if self.op == "delete":
            for row in matched:
                self.store.rows.remove(row)
            return FakeResponse([{"id": row["id"]} for row in matched])

        if self.order_column:
            matched.sort(key=lambda r: r[self.order_column], reverse=self.descending)
        if self.max_rows is not None:
            matched = matched[: self.max_rows]
        return FakeResponse([self._project(row) for row in matched])


class FakeTable:
    def __init__(self, store: "FakeStore") -> None:
        self.store = store

    def insert(self, payload: dict) -> FakeQuery:
        query = FakeQuery(self.store, "insert")
        query.payload = payload
        return query

    def select(self, columns: str = "*") -> FakeQuery:
        return FakeQuery(self.store, "select", columns)

    def delete(self) -> FakeQuery:
        return FakeQuery(self.store, "delete")


class FakeStore:
    """Stands in for supabase.AsyncClient.

    `fail_on` is a set of operations ("insert", "select", "delete") that raise
    instead of running, so each failure path is provoked independently.
    """

    def __init__(self, rows: list[dict] | None = None, fail_on: set[str] | None = None):
        self.rows = rows or []
        self.fail_on = fail_on or set()
        self.operations: list[tuple[str, str]] = []

    def table(self, name: str) -> FakeTable:
        assert name == history.TABLE, f"unexpected table {name}"
        return FakeTable(self)


# ---------------------------------------------------------------- fixtures


def sample_result(*, skipped: bool = False) -> AnalysisResult:
    """A realistic AnalysisResult, aggregate built by the real aggregator."""
    analysis = ChunkAnalysis(
        summary="This section caps liability and waives a jury trial.",
        risk_flags=[
            RiskFlag(
                clause_type="Limitation of Liability",
                severity=RiskLevel.HIGH,
                explanation="Liability for confidentiality breaches is uncapped.",
                page_reference=2,
            ),
            RiskFlag(
                clause_type="Jury Trial Waiver",
                severity=RiskLevel.MEDIUM,
                explanation="Both parties give up the right to a jury trial.",
                page_reference=3,
            ),
        ],
        missing_clauses=[
            MissingClause(
                clause_name="Governing Law",
                importance=RiskLevel.MEDIUM,
                explanation="No jurisdiction is named for disputes.",
            )
        ],
        document_type="NDA",
    )
    failures = (
        [
            ChunkFailure(
                chunk_index=1,
                reason=ChunkFailureReason.TRUNCATED,
                user_message="One section was too long to analyze in one pass.",
                detail=LEAK_MARKER,
            )
        ]
        if skipped
        else []
    )
    run_obj = AnalysisRun(
        analyzed=[AnalyzedChunk(chunk_index=0, analysis=analysis)],
        failures=failures,
        document_type_hint="NDA",
    )
    return AnalysisResult(
        document=DocumentMeta(
            filename="mutual-nda.pdf",
            size_bytes=48_120,
            page_count=4,
            pages_with_text=4,
            extraction_method=ExtractionMethod.PDFPLUMBER,
            chunk_count=2 if skipped else 1,
        ),
        document_type_hint="NDA",
        # Built by the real aggregator so the stored summary columns cannot drift
        # from what the results page shows.
        aggregate=aggregate_run(run_obj),
        pages=[PageText(page_number=n, text=f"Page {n} text.") for n in range(1, 5)],
        sections=[
            SectionAnalysis(chunk_index=0, pages=[1, 2, 3], analysis=analysis)
        ],
        skipped=[
            SkippedSection(
                chunk_index=f.chunk_index,
                reason=f.reason,
                message=f.user_message,
                pages=[4],
            )
            for f in failures
        ],
    )


def stored_row(result: AnalysisResult, *, age_days: float = 0.0) -> dict:
    created = datetime.now(timezone.utc) - timedelta(days=age_days)
    row = history._row(result)
    row["id"] = str(uuid.uuid4())
    row["created_at"] = created.isoformat()
    return row


# ---------------------------------------------------------------- checks


def main_tests() -> int:
    r = Results("history")

    # ------------------------------------------------------------- save
    r.section("save")

    result = sample_result()
    store = FakeStore()
    saved_id = run(save_analysis(store, result))
    row = store.rows[0]

    r.check("save returns the new id", saved_id == row["id"])
    r.check("summary columns come from the aggregate",
            row["risk_flag_count"] == 2 and row["missing_clause_count"] == 1,
            f"{row['risk_flag_count']} flags, {row['missing_clause_count']} missing")
    r.check("document type is stored", row["document_type"] == "NDA")
    r.check("filename and page count are stored",
            row["filename"] == "mutual-nda.pdf" and row["page_count"] == 4)
    r.check("extraction method is stored as its string value",
            row["extraction_method"] == "pdfplumber")
    r.check("the serialized result is JSON-ready",
            isinstance(row["result"], dict) and row["result"]["document_type_hint"] == "NDA")

    r.check("no client means no save, and no error", run(save_analysis(None, result)) is None)

    # The rule this whole module is built around. Caught rather than allowed to
    # propagate: `save_analysis` raising is exactly the defect under test, and an
    # uncaught exception here would abort the module before the checks that matter
    # most — at the bottom — ever run.
    def save_result(store):
        try:
            return run(save_analysis(store, result))
        except Exception as exc:  # noqa: BLE001 - the failure IS the finding
            return exc

    r.check("an insert failure returns None instead of raising",
            save_result(FakeStore(fail_on={"insert"})) is None)

    # A purge failure must not cost us the row we came to write.
    saved_despite_purge = save_result(FakeStore(fail_on={"delete"}))
    r.check("a purge failure still saves", isinstance(saved_despite_purge, str))

    # ------------------------------------------------------------- retention
    r.section("retention")

    fresh = stored_row(result, age_days=1)
    stale = stored_row(result, age_days=HISTORY_RETENTION_DAYS + 1)
    store = FakeStore(rows=[fresh, stale])
    run(save_analysis(store, result))
    remaining = {row["id"] for row in store.rows}

    r.check("a row past the retention window is purged", stale["id"] not in remaining)
    r.check("a row inside the window survives", fresh["id"] in remaining)
    r.check("purging happens as well as the insert, not instead of it", len(store.rows) == 2)
    # Order matters, and not cosmetically. save_analysis runs after the job is
    # already COMPLETE, so anything queried before the insert is a window in which
    # a reader opening their history does not see the analysis they just ran.
    r.check("the insert goes first, so the row lands as early as possible",
            [op for op, _ in store.operations] == ["insert", "delete"],
            str([op for op, _ in store.operations]))

    # ------------------------------------------------------------- list
    r.section("list")

    older = stored_row(result, age_days=5)
    newer = stored_row(result, age_days=1)
    store = FakeStore(rows=[older, newer])
    entries = run(list_analyses(store, HISTORY_PAGE_SIZE))

    # Asserted first, and on the query rather than on the rows: selecting `result`
    # also breaks validation (HistoryEntry forbids extra fields), and a crash two
    # checks later would report "the list is empty" for what is really "the list
    # query ships an entire document's text per row".
    selected = [columns for op, columns in store.operations if op == "select"]
    r.check("the list query never pulls the document text",
            bool(selected) and all("result" not in columns.split(",") for columns in selected),
            selected[0] if selected else "no select recorded")

    r.check("both rows are listed", len(entries) == 2)
    r.check("newest first", bool(entries) and entries[0].id == newer["id"])
    r.check("summary fields survive the round trip",
            bool(entries)
            and entries[0].filename == "mutual-nda.pdf"
            and entries[0].risk_flag_count == 2)

    # A row whose columns all exist but whose values no longer validate — what a
    # schema change actually produces. postgrest returns nulls for missing columns,
    # never absent keys, so this is the realistic shape of a bad row.
    malformed = stored_row(result, age_days=2)
    malformed["page_count"] = None
    store = FakeStore(rows=[older, malformed])
    entries = run(list_analyses(store, HISTORY_PAGE_SIZE))
    r.check("one malformed row does not blank the list", len(entries) == 1)
    r.check("the surviving row is the good one", bool(entries) and entries[0].id == older["id"])

    broken = FakeStore(fail_on={"select"})
    try:
        run(list_analyses(broken, HISTORY_PAGE_SIZE))
        raised = None
    except HistoryError as exc:
        raised = exc
    r.check("an unreachable database raises rather than returning []", raised is not None)
    r.check("the user message does not carry the internal detail",
            raised is not None and LEAK_MARKER not in raised.user_message)
    r.check("the internal detail is kept for the log",
            raised is not None and LEAK_MARKER in raised.detail)

    # ------------------------------------------------------------- fetch
    r.section("fetch")

    with_skip = sample_result(skipped=True)
    store = FakeStore(rows=[stored_row(with_skip)])
    fetched = run(get_analysis(store, store.rows[0]["id"]))

    r.check("a stored analysis round-trips unchanged",
            fetched is not None
            and fetched.model_dump(mode="json") == with_skip.model_dump(mode="json"))
    r.check("the skipped section survives storage", fetched is not None and len(fetched.skipped) == 1)
    r.check("ChunkFailure.detail is still absent after a round trip",
            "detail" not in fetched.skipped[0].model_dump())

    r.check("an unknown id is None", run(get_analysis(store, str(uuid.uuid4()))) is None)

    store = FakeStore(rows=[stored_row(result)])
    r.check("a malformed id is None", run(get_analysis(store, "not-a-uuid")) is None)
    # The load-bearing half. FakeStore tolerates a non-uuid id by simply not
    # matching it, where real postgrest answers with an error — which would surface
    # as "history unavailable" for what is plainly a bad id. So the guard is checked
    # by asserting the query is never issued, not by the value that comes back.
    r.check("a malformed id never reaches the database", store.operations == [])

    bad_row = stored_row(result)
    bad_row["result"] = {"document": "this is not an AnalysisResult"}
    store = FakeStore(rows=[bad_row])
    try:
        run(get_analysis(store, bad_row["id"]))
        stale_error = None
    except StaleAnalysisError as exc:
        stale_error = exc
    r.check("a row from an older schema raises rather than returning empty findings",
            stale_error is not None)

    # ------------------------------------------------------------- delete
    r.section("delete")

    target = stored_row(result)
    store = FakeStore(rows=[target, stored_row(result)])
    r.check("deleting an existing row reports True", run(delete_analysis(store, target["id"])) is True)
    r.check("the row is gone", all(row["id"] != target["id"] for row in store.rows))
    r.check("only the targeted row is deleted", len(store.rows) == 1)
    r.check("deleting it again reports False", run(delete_analysis(store, target["id"])) is False)
    r.check("a malformed id reports False", run(delete_analysis(store, "nope")) is False)

    # ------------------------------------------------------------- endpoints
    r.section("endpoints")

    with TestClient(main.app) as client:
        client.app.state.supabase = None
        unconfigured = client.get("/api/documents/history")
        r.check("history is 503 when Supabase is not configured", unconfigured.status_code == 503)
        r.check("the 503 says analysis is unaffected",
                "analysis are unaffected" in unconfigured.json()["detail"])
        r.check("health reports history as unavailable",
                client.get("/api/health").json()["history_available"] is False)

        store = FakeStore(rows=[stored_row(with_skip), stored_row(result, age_days=2)])
        client.app.state.supabase = store

        listed = client.get("/api/documents/history")
        body = listed.json()
        r.check("history lists stored analyses", listed.status_code == 200 and len(body["entries"]) == 2)
        r.check("the page reports the limit it applied", body["limit"] == HISTORY_PAGE_SIZE)
        r.check("no entry carries the document text",
                all("result" not in entry for entry in body["entries"]))

        r.check("health reports history as available",
                client.get("/api/health").json()["history_available"] is True)
        r.check("health reports the retention the server enforces",
                client.get("/api/health").json()["history_retention_days"] == HISTORY_RETENTION_DAYS)

        over_limit = client.get("/api/documents/history", params={"limit": HISTORY_PAGE_SIZE + 1})
        r.check("a client cannot ask for more than the page size", over_limit.status_code == 422)
        r.check("the validation message is not upload-specific",
                "PDF" not in over_limit.json()["detail"])

        entry_id = body["entries"][0]["id"]
        detail = client.get(f"/api/documents/history/{entry_id}")
        r.check("a stored analysis is fetchable by id", detail.status_code == 200)
        r.check("it arrives in the same shape a completed job returns",
                set(detail.json()) == set(AnalysisResult.model_fields))
        skipped_payload = detail.json()["skipped"]
        r.check("the wire form still omits ChunkFailure.detail",
                all("detail" not in section for section in skipped_payload))
        r.check("the leak marker never reaches the wire", LEAK_MARKER not in detail.text)

        r.check("an unknown id is 404",
                client.get(f"/api/documents/history/{uuid.uuid4()}").status_code == 404)
        r.check("a malformed id is 404, not 500",
                client.get("/api/documents/history/not-a-uuid").status_code == 404)

        removed = client.delete(f"/api/documents/history/{entry_id}")
        r.check("delete returns 204", removed.status_code == 204)
        r.check("the deleted analysis is then 404",
                client.get(f"/api/documents/history/{entry_id}").status_code == 404)
        r.check("deleting it twice is 404",
                client.delete(f"/api/documents/history/{entry_id}").status_code == 404)

        client.app.state.supabase = FakeStore(fail_on={"select"})
        down = client.get("/api/documents/history")
        r.check("a database failure is 503, never an empty list", down.status_code == 503)
        r.check("the 503 body carries no internal detail", LEAK_MARKER not in down.text)

    # ------------------------------------------------------- analysis is safe
    r.section("a storage failure never costs an analysis")

    analysis = ChunkAnalysis(
        summary="This section limits liability.",
        risk_flags=[
            RiskFlag(
                clause_type="Limitation of Liability",
                severity=RiskLevel.HIGH,
                explanation="Liability is uncapped for confidentiality breaches.",
                page_reference=1,
            )
        ],
        missing_clauses=[],
        document_type="NDA",
    )
    pdf = make_text_pdf(
        [
            "LIMITATION OF LIABILITY. In no event shall the Disclosing Party be "
            "liable for indirect damages, provided that liability for breach of "
            "confidentiality shall be unlimited and uncapped. " * 6
        ]
    )

    with TestClient(main.app) as client:
        client.app.state.claude_client = FakeClient([stub_response("end_turn", analysis)])
        client.app.state.supabase = FakeStore(fail_on={"insert", "select", "delete"})

        accepted = client.post(
            "/api/documents/analyze",
            files={"file": ("nda.pdf", pdf, "application/pdf")},
        )
        job_id = accepted.json()["job_id"]

        state: dict = {}
        for _ in range(500):
            state = client.get(f"/api/documents/analyze/{job_id}").json()
            if state["status"] in (JobStatus.COMPLETE.value, JobStatus.FAILED.value):
                break

        r.check("the job still completes when every storage call fails",
                state.get("status") == JobStatus.COMPLETE.value, state.get("error") or "")
        r.check("the result is intact",
                bool(state.get("result", {}).get("aggregate", {}).get("risk_flags")))

    return r.finish()


if __name__ == "__main__":
    sys.exit(main_tests())
