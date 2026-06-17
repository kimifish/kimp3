from pathlib import Path

from rich.console import Console

from kimp3.executor import ExecutionResult
from kimp3.models import AudioTags, FileOperation
from kimp3.planning import OperationPlan, PathPlan, build_tag_change_plan
from kimp3.reporting import (
    ExecutionReporter,
    PlanReporter,
    execution_result_to_report_dict,
    operation_plan_to_report_dict,
    plan_status,
)


def make_plan(status: str = "ok") -> OperationPlan:
    plan = OperationPlan(
        path=PathPlan(
            source_path=Path("incoming/song.mp3"),
            target_path=Path("library/Artist/song.mp3"),
            genre_links=[Path("library/_Genres/Rock/song.mp3")],
            operation=FileOperation.COPY,
        ),
        tags=build_tag_change_plan(AudioTags(title="Old"), AudioTags(title="New")),
    )
    if status == "error":
        plan.errors.append("bad target")
    elif status == "skip":
        plan.skip_execution = True
        plan.skip_reason = "existing target kept"
    elif status == "replace":
        plan.replace_existing = True
    elif status == "warning":
        plan.warnings.append("duplicate track number")
    return plan


def test_plan_reporter_renders_summary_table_and_details():
    console = Console(record=True, width=120)
    plans = [make_plan("ok"), make_plan("replace"), make_plan("error")]

    reporter = PlanReporter(console)
    reporter.print_full_preview(plans, title="Preview")
    output = console.export_text()

    assert "Preview Summary" in output
    assert "Operation Plan" not in output  # title is exactly Preview for the table
    assert "Preview" in output
    assert "replace" in output
    assert "bad target" in output
    assert "title" in output


def test_execution_reporter_renders_result_and_failures():
    console = Console(record=True, width=100)
    result = ExecutionResult(successes=2, failures=1, skips=3, errors=["failed verify"])

    ExecutionReporter(console).print_result(result)
    output = console.export_text()

    assert "Execution Result" in output
    assert "success" in output
    assert "failed verify" in output


def test_report_serializers_are_json_ready():
    plan = make_plan("skip")
    result = ExecutionResult(successes=1, failures=0, skips=1)

    plan_dict = operation_plan_to_report_dict(plan)
    result_dict = execution_result_to_report_dict(result)

    assert plan_status(plan)[0] == "skip"
    assert plan_dict["operation"] == "copy"
    assert plan_dict["status"] == "skip"
    assert plan_dict["tag_changes"][0]["field"] == "title"
    assert result_dict == {"successes": 1, "failures": 0, "skips": 1, "errors": []}
    assert result.to_report_dict() == result_dict
