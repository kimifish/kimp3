from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from kimp3.planning import OperationPlan


def _console(console: Console | None = None) -> Console:
    if console is not None:
        return console
    try:
        from kimp3.config import cfg

        return cfg.runtime.console or Console(width=120)
    except Exception:
        return Console(width=120)


def operation_plan_to_report_dict(plan: OperationPlan) -> dict[str, Any]:
    """Serialize an operation plan into JSON-ready data."""
    status, reason = plan_status(plan)
    return {
        "operation": plan.operation.value,
        "status": status,
        "source": str(plan.path.source_path),
        "target": str(plan.path.target_path),
        "requires_tag_write": plan.requires_tag_write,
        "requires_file_operation": plan.requires_file_operation,
        "replace_existing": plan.replace_existing,
        "skip_execution": plan.skip_execution,
        "reason": reason,
        "tag_changes": [change.model_dump() for change in plan.tags.changes],
        "genre_links": [str(link) for link in plan.path.genre_links],
        "warnings": list(plan.warnings),
        "errors": list(plan.errors),
    }


def execution_result_to_report_dict(result: object) -> dict[str, Any]:
    """Serialize an ExecutionResult-like object into JSON-ready data."""
    return {
        "successes": getattr(result, "successes", 0),
        "failures": getattr(result, "failures", 0),
        "skips": getattr(result, "skips", 0),
        "errors": list(getattr(result, "errors", [])),
    }


def plan_status(plan: OperationPlan) -> tuple[str, str]:
    """Return display status and reason for an operation plan."""
    if plan.errors:
        return "error", "; ".join(plan.errors)
    if plan.skip_execution:
        return "skip", plan.skip_reason
    if plan.replace_existing:
        return "replace", "replace existing target"
    if plan.is_noop:
        return "noop", "already correct"
    if plan.warnings:
        return "warning", "; ".join(plan.warnings)
    return "ok", ""


class PlanReporter:
    """Rich renderer for OperationPlan previews."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = _console(console)

    def print_summary(self, plans: list[OperationPlan], title: str = "Plan Summary") -> None:
        counts = self._summary_counts(plans)
        table = Table(title=title, show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right")
        for key in ["copy", "move", "none", "noop", "ok", "replace", "skip", "warning", "error"]:
            table.add_row(key, str(counts.get(key, 0)))
        self.console.print(table)

    def print_plan_table(self, plans: list[OperationPlan], title: str = "Operation Plan") -> None:
        table = Table(title=title, show_header=True, header_style="bold magenta")
        table.add_column("OP", style="cyan", no_wrap=True)
        table.add_column("STATUS", no_wrap=True)
        table.add_column("SOURCE", overflow="fold")
        table.add_column("TARGET", overflow="fold")
        table.add_column("TAGS", justify="right")
        table.add_column("LINKS", justify="right")
        table.add_column("REASON", overflow="fold")
        for plan in plans:
            status, reason = plan_status(plan)
            table.add_row(
                plan.operation.value,
                self._styled_status(status),
                self._short_path(plan.path.source_path),
                self._short_path(plan.path.target_path),
                str(len(plan.tags.changes)),
                str(len(plan.path.genre_links)),
                reason or "-",
            )
        self.console.print(table)

    def print_interesting_details(self, plans: list[OperationPlan]) -> None:
        for plan in plans:
            status, _reason = plan_status(plan)
            if status in {"error", "warning", "replace", "skip"}:
                self.print_plan_detail(plan)

    def print_plan_detail(self, plan: OperationPlan) -> None:
        status, reason = plan_status(plan)
        lines = [
            f"[cyan]Source:[/] {plan.path.source_path}",
            f"[cyan]Target:[/] {plan.path.target_path}",
        ]
        if reason:
            lines.append(f"[yellow]Reason:[/] {reason}")
        if plan.tags.changes:
            lines.append("\n[bold]Tag changes:[/]")
            for change in plan.tags.changes:
                lines.append(f"  [cyan]{change.field}[/]: {change.old_value!r} -> {change.new_value!r}")
        if plan.path.genre_links:
            lines.append("\n[bold]Genre symlinks:[/]")
            for link in plan.path.genre_links:
                lines.append(f"  + {link}")
        if plan.warnings:
            lines.append("\n[bold yellow]Warnings:[/]")
            lines.extend(f"  {warning}" for warning in plan.warnings)
        if plan.errors:
            lines.append("\n[bold red]Errors:[/]")
            lines.extend(f"  {error}" for error in plan.errors)
        self.console.print(Panel("\n".join(lines), title=f"{status}: {plan.operation.value}", border_style=self._border(status)))

    def print_full_preview(self, plans: list[OperationPlan], title: str = "Dry Run Preview") -> None:
        self.print_summary(plans, title=f"{title} Summary")
        self.print_plan_table(plans, title=title)
        self.print_interesting_details(plans)

    def _summary_counts(self, plans: list[OperationPlan]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for plan in plans:
            counts[plan.operation.value] = counts.get(plan.operation.value, 0) + 1
            status, _reason = plan_status(plan)
            counts[status] = counts.get(status, 0) + 1
        return counts

    def _short_path(self, path: Path) -> str:
        return str(path)

    def _styled_status(self, status: str) -> str:
        style = {
            "ok": "green",
            "noop": "green",
            "replace": "magenta",
            "skip": "yellow",
            "warning": "yellow",
            "error": "red",
        }.get(status, "white")
        return f"[{style}]{status}[/]"

    def _border(self, status: str) -> str:
        return {
            "ok": "green",
            "noop": "green",
            "replace": "magenta",
            "skip": "yellow",
            "warning": "yellow",
            "error": "red",
        }.get(status, "white")


class ExecutionReporter:
    """Rich renderer for execution results."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = _console(console)

    def print_result(self, result: object, title: str = "Execution Result") -> None:
        table = Table(title=title, show_header=True, header_style="bold magenta", min_width=80)
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right")
        table.add_row("success", str(getattr(result, "successes", 0)))
        table.add_row("skipped", str(getattr(result, "skips", 0)))
        table.add_row("failed", str(getattr(result, "failures", 0)))
        self.console.print(table)
        errors = list(getattr(result, "errors", []))
        if errors:
            self.console.print(Panel("\n".join(errors), title="Failures", border_style="red"))
