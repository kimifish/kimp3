from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile
from pydantic import BaseModel, ConfigDict, Field

from kimp3.models import AudioTags, FileOperation
from kimp3.strings_operations import sanitize_path_component


class PathPlan(BaseModel):
    """Planned filesystem locations for one audio file."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    source_path: Path
    target_path: Path
    genre_links: list[Path] = Field(default_factory=list)
    operation: FileOperation
    warnings: list[str] = Field(default_factory=list)


class TagFieldChange(BaseModel):
    """One managed tag field diff."""

    field: str
    old_value: Any = None
    new_value: Any = None


class TagChangePlan(BaseModel):
    """Planned managed tag changes for one audio file."""

    source_tags: AudioTags
    target_tags: AudioTags
    changes: list[TagFieldChange] = Field(default_factory=list)

    @property
    def requires_write(self) -> bool:
        """Return True when managed tags differ."""
        return bool(self.changes)


class OperationPlan(BaseModel):
    """Complete operation plan for one audio file."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: PathPlan
    tags: TagChangePlan
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    skip_execution: bool = False
    skip_reason: str = ""
    replace_existing: bool = False

    @property
    def operation(self) -> FileOperation:
        return self.path.operation

    @property
    def requires_tag_write(self) -> bool:
        return self.tags.requires_write and self.operation != FileOperation.NONE

    @property
    def requires_file_operation(self) -> bool:
        return self.operation in {FileOperation.COPY, FileOperation.MOVE} and self.path.source_path != self.path.target_path

    @property
    def is_noop(self) -> bool:
        return not self.requires_tag_write and not self.requires_file_operation and not self.path.genre_links


class CandidateQuality(BaseModel):
    """Heuristic quality score for duplicate/conflict resolution."""

    path: Path
    score: float
    reasons: list[str] = Field(default_factory=list)


class ConflictDecision(BaseModel):
    """Decision made for one conflict group."""

    target_path: Path
    action: str
    winner: Path | None = None
    losers: list[Path] = Field(default_factory=list)
    reason: str = ""


class PlanValidationError(ValueError):
    """Raised when a plan cannot be safely executed."""


KNOWN_PATTERN_VARIABLES = {
    "song_title",
    "song_artist",
    "album_title",
    "album_artist",
    "track_num",
    "num_of_tracks",
    "disc_num",
    "genre",
    "year",
    "ext",
}

CONDITIONAL_PATTERN = re.compile(r"%\?([A-Za-z_][A-Za-z0-9_]*)\{([^{}]*)\}")


def is_inside_collection(source_path: Path, collection_dir: Path) -> bool:
    """Return True when source_path is collection_dir or below it."""
    source = source_path.resolve()
    collection = collection_dir.resolve()
    return source == collection or collection in source.parents


def resolve_operation(
    requested: FileOperation,
    source_path: Path,
    collection_dir: Path,
    force_external_move: bool = False,
) -> FileOperation:
    """Resolve auto/copy/move/none using source context."""
    if requested == FileOperation.AUTO:
        return FileOperation.MOVE if is_inside_collection(source_path, collection_dir) else FileOperation.COPY
    if requested == FileOperation.MOVE and not is_inside_collection(source_path, collection_dir) and not force_external_move:
        raise PlanValidationError("Moving external source requires scan.force_external_move=true")
    return requested


def validate_pattern_variables(pattern: str) -> None:
    """Reject unknown %variables before touching the filesystem."""
    unknown = sorted(
        set(re.findall(r"%([A-Za-z_][A-Za-z0-9_]*)", pattern))
        - KNOWN_PATTERN_VARIABLES
    )
    unknown.extend(
        field
        for field in sorted(
            set(re.findall(r"%\?([A-Za-z_][A-Za-z0-9_]*)\{", pattern))
            - KNOWN_PATTERN_VARIABLES
        )
        if field not in unknown
    )
    if unknown:
        raise PlanValidationError(f"Unknown pattern variables: {', '.join(unknown)}")


def build_tag_mapping(tags: AudioTags, source_path: Path) -> dict[str, str]:
    """Build sanitized values used by path rendering."""
    ext = source_path.suffix.lower().lstrip(".")
    return {
        "song_title": sanitize_path_component(str(tags.title).strip()),
        "song_artist": sanitize_path_component(str(tags.artist).strip()),
        "album_title": sanitize_path_component(str(tags.album).strip()),
        "album_artist": sanitize_path_component(str(tags.album_artist).strip()),
        "track_num": str(tags.track_number).zfill(2) if tags.track_number else "XX",
        "num_of_tracks": str(tags.total_tracks) if tags.total_tracks else "XX",
        "disc_num": str(tags.disc_number) if tags.disc_number else "1",
        "genre": sanitize_path_component(str(tags.genre).strip()),
        "year": str(tags.year) if tags.year else "XXXX",
        "ext": ext,
    }


def build_condition_mapping(tags: AudioTags, source_path: Path) -> dict[str, bool]:
    """Build field presence flags used by conditional path fragments."""
    return {
        "song_title": bool(tags.title),
        "song_artist": bool(tags.artist),
        "album_title": bool(tags.album),
        "album_artist": bool(tags.album_artist),
        "track_num": bool(tags.track_number),
        "num_of_tracks": bool(tags.total_tracks),
        "disc_num": bool(
            tags.disc_number and tags.total_discs and int(tags.total_discs) > 1
        ),
        "genre": bool(tags.genre),
        "year": bool(tags.year),
        "ext": bool(source_path.suffix),
    }


def render_pattern(
    pattern: str,
    mapping: dict[str, str],
    conditions: dict[str, bool] | None = None,
) -> Path:
    """Render a slash-separated pattern into a relative sanitized path."""
    validate_pattern_variables(pattern)
    conditions = conditions or {field: bool(value) for field, value in mapping.items()}

    def render_conditional(match: re.Match[str]) -> str:
        field, content = match.groups()
        return content if conditions.get(field, False) else ""

    rendered = CONDITIONAL_PATTERN.sub(render_conditional, pattern)
    for variable, value in mapping.items():
        rendered = rendered.replace(f"%{variable}", value or "Unknown")
    parts = [sanitize_path_component(part) for part in rendered.split("/") if part]
    return Path(*parts)


def build_path_plan(
    source_path: Path,
    tags: AudioTags,
    song_dir: object,
    settings: object,
) -> PathPlan:
    """Build target path, genre links, and resolved operation without side effects."""
    collection_dir = Path(settings.collection.directory)
    operation = resolve_operation(
        settings.scan.operation,
        source_path,
        collection_dir,
        settings.scan.force_external_move,
    )

    album_pattern = settings.paths.patterns.compilation if getattr(song_dir, "is_compilation", False) else settings.paths.patterns.album
    genre_pattern = settings.paths.patterns.genre

    mapping = build_tag_mapping(tags, source_path)
    conditions = build_condition_mapping(tags, source_path)
    target_path = source_path if operation == FileOperation.NONE else collection_dir / render_pattern(album_pattern, mapping, conditions)
    if operation != FileOperation.NONE and target_path.suffix.lower() != source_path.suffix.lower():
        raise PlanValidationError(f"Target extension {target_path.suffix} differs from source extension {source_path.suffix}")

    genre_links: list[Path] = []
    allow_none_links = getattr(settings.scan, "create_symlinks_in_none", False)
    if settings.collection.create_genre_links and tags.genre and (operation != FileOperation.NONE or allow_none_links):
        for genre in str(tags.genre).split(","):
            genre_mapping = dict(mapping)
            genre_mapping["genre"] = sanitize_path_component(genre.strip())
            genre_conditions = dict(conditions)
            genre_conditions["genre"] = bool(genre.strip())
            genre_links.append(collection_dir / render_pattern(genre_pattern, genre_mapping, genre_conditions))

    return PathPlan(source_path=source_path, target_path=target_path, genre_links=genre_links, operation=operation)


MANAGED_TAG_FIELDS = [
    "title",
    "artist",
    "album",
    "album_artist",
    "track_number",
    "total_tracks",
    "disc_number",
    "total_discs",
    "year",
    "genres",
    "lastfm_tags",
    "comment",
    "compilation",
    "rating",
    "artwork",
    "lyrics",
    "lyrics_lookup",
]


def _tag_value(tags: AudioTags, field: str) -> Any:
    value = getattr(tags, field)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def build_tag_change_plan(source_tags: AudioTags, target_tags: AudioTags) -> TagChangePlan:
    """Build managed tag diff without filesystem side effects."""
    changes = []
    for field in MANAGED_TAG_FIELDS:
        old_value = _tag_value(source_tags, field)
        new_value = _tag_value(target_tags, field)
        if old_value != new_value:
            changes.append(TagFieldChange(field=field, old_value=old_value, new_value=new_value))
    return TagChangePlan(source_tags=source_tags, target_tags=target_tags, changes=changes)


def build_operation_plan(
    source_path: Path,
    source_tags: AudioTags,
    target_tags: AudioTags,
    song_dir: object,
    settings: object,
) -> OperationPlan:
    """Build a complete path+tag operation plan for one audio file."""
    path_plan = build_path_plan(source_path, target_tags, song_dir, settings)
    tag_plan = build_tag_change_plan(source_tags, target_tags)
    return OperationPlan(path=path_plan, tags=tag_plan, warnings=[*path_plan.warnings])


def validate_audio_plans(plans: list[PathPlan]) -> list[str]:
    """Return pre-execution validation errors for planned paths."""
    from kimp3.backends import get_backend

    errors: list[str] = []
    targets: dict[Path, Path] = {}
    for plan in plans:
        if plan.operation == FileOperation.NONE:
            continue
        target = plan.target_path.resolve(strict=False)
        source = plan.source_path.resolve(strict=False)
        if target in targets and targets[target] != source:
            errors.append(f"Duplicate target path: {target}")
        targets[target] = source
        if target.exists() and target != source:
            try:
                same_file = os.path.samefile(plan.source_path, plan.target_path)
            except OSError:
                same_file = False
            if not same_file:
                errors.append(f"Target already exists: {target}")
        try:
            get_backend(plan.source_path)
        except ValueError as error:
            errors.append(str(error))
    return errors


def validate_operation_plans(plans: list[OperationPlan]) -> list[str]:
    """Validate complete operation plans before execution."""
    resolve_operation_conflicts(plans)
    return [error for plan in plans for error in plan.errors]


def render_operation_preview(plan: OperationPlan) -> list[str]:
    """Return read-only preview lines for dry-run/none/report output."""
    lines = [
        f"operation: {plan.operation.value}",
        f"source: {plan.path.source_path}",
        f"target: {plan.path.target_path}",
    ]
    if plan.skip_execution:
        lines.append(f"skip: {plan.skip_reason}")
    if plan.replace_existing:
        lines.append("replace_existing: true")
    if plan.tags.changes:
        lines.append("tag changes:")
        for change in plan.tags.changes:
            lines.append(f"  {change.field}: {change.old_value!r} -> {change.new_value!r}")
    else:
        lines.append("tag changes: none")
    if plan.path.genre_links:
        lines.append("genre symlinks:")
        lines.extend(f"  {link}" for link in plan.path.genre_links)
    else:
        lines.append("genre symlinks: none")
    for warning in plan.warnings:
        lines.append(f"warning: {warning}")
    for error in plan.errors:
        lines.append(f"error: {error}")
    return lines


FORMAT_SCORE = {
    ".flac": 100.0,
    ".mp3": 50.0,
}


def score_candidate(path: Path, tags: AudioTags | None = None, existing_library_file: bool = False) -> CandidateQuality:
    """Score one candidate for keep-best conflict resolution."""
    score = FORMAT_SCORE.get(path.suffix.lower(), 0.0)
    reasons = [f"format={path.suffix.lower() or '<none>'}:{score:.0f}"]
    try:
        audio = MutagenFile(path)
        info = getattr(audio, "info", None)
        bitrate = int(getattr(info, "bitrate", 0) or 0)
        length = float(getattr(info, "length", 0.0) or 0.0)
        if bitrate:
            bitrate_score = min(bitrate / 10000.0, 40.0)
            score += bitrate_score
            reasons.append(f"bitrate={bitrate}:{bitrate_score:.1f}")
        if length:
            score += min(length / 60.0, 10.0)
            reasons.append(f"duration={length:.1f}")
    except Exception as error:
        reasons.append(f"audio-info-unavailable:{error}")
    try:
        size_score = min(path.stat().st_size / (1024 * 1024), 25.0)
        score += size_score
        reasons.append(f"size={path.stat().st_size}:{size_score:.1f}")
    except OSError as error:
        reasons.append(f"size-unavailable:{error}")
    if tags:
        completeness_fields = [
            tags.title,
            tags.artist,
            tags.album,
            tags.album_artist,
            tags.track_number,
            tags.total_tracks,
            tags.year,
            tags.genres,
            tags.artwork,
            tags.lyrics,
        ]
        completeness = sum(1 for value in completeness_fields if value)
        score += completeness * 3.0
        reasons.append(f"tag-completeness={completeness}")
    if existing_library_file:
        score += 8.0
        reasons.append("existing-library-bonus=8")
    return CandidateQuality(path=path, score=score, reasons=reasons)


def resolve_operation_conflicts(plans: list[OperationPlan]) -> list[ConflictDecision]:
    """Resolve duplicate target and target-exists conflicts with keep-best policy."""
    from kimp3.config import cfg

    policy = cfg.scan.conflict_policy
    decisions: list[ConflictDecision] = []
    for plan in plans:
        plan.errors.clear()
        plan.warnings = [warning for warning in plan.warnings if not warning.startswith("Conflict:")]
        plan.skip_execution = False
        plan.skip_reason = ""
        plan.replace_existing = False
        if plan.operation == FileOperation.NONE:
            continue
        try:
            from kimp3.backends import get_backend

            get_backend(plan.path.source_path)
        except ValueError as error:
            plan.errors.append(str(error))
        if not plan.path.source_path.exists():
            plan.errors.append(f"Source does not exist: {plan.path.source_path}")
        elif not os.access(plan.path.source_path, os.R_OK):
            plan.errors.append(f"Source is not readable: {plan.path.source_path}")
        if plan.path.target_path.parent.exists() and not plan.path.target_path.parent.is_dir():
            plan.errors.append(f"Target parent exists and is not a directory: {plan.path.target_path.parent}")
        nearest_parent = plan.path.target_path.parent
        while not nearest_parent.exists() and nearest_parent != nearest_parent.parent:
            nearest_parent = nearest_parent.parent
        if nearest_parent.exists() and not os.access(nearest_parent, os.W_OK):
            plan.errors.append(f"Target parent is not writable: {nearest_parent}")
        if plan.path.target_path.exists() and plan.path.target_path.is_dir():
            plan.errors.append(f"Target path exists and is a directory: {plan.path.target_path}")
        tmp_path = plan.path.target_path.with_name(f".{plan.path.target_path.stem}.tmp-kimp3{plan.path.target_path.suffix}")
        if tmp_path.exists():
            plan.errors.append(f"Temporary target already exists: {tmp_path}")

    target_groups: dict[Path, list[OperationPlan]] = {}
    for plan in plans:
        if plan.operation != FileOperation.NONE and not plan.errors:
            target_groups.setdefault(plan.path.target_path.resolve(strict=False), []).append(plan)

    for target, group in target_groups.items():
        if len(group) > 1:
            if policy == "fail":
                for plan in group:
                    plan.errors.append(f"Duplicate target path: {target}")
                continue
            if policy == "skip":
                for plan in group:
                    plan.skip_execution = True
                    plan.skip_reason = f"Conflict: duplicate target skipped: {target}"
                    plan.warnings.append(plan.skip_reason)
                decisions.append(
                    ConflictDecision(
                        target_path=target,
                        action="skip-duplicates",
                        losers=[plan.path.source_path for plan in group],
                        reason="duplicate planned target",
                    )
                )
                continue
            if policy == "suffix":
                for index, plan in enumerate(group[1:], start=1):
                    plan.path.target_path = _suffix_path(plan.path.target_path, index)
                    plan.warnings.append(f"Conflict: duplicate target renamed to {plan.path.target_path}")
                decisions.append(
                    ConflictDecision(
                        target_path=target,
                        action="suffix-duplicates",
                        winner=group[0].path.source_path,
                        losers=[plan.path.source_path for plan in group[1:]],
                        reason="duplicate planned target",
                    )
                )
                continue
            winner = max(group, key=lambda item: score_candidate(item.path.source_path, item.tags.target_tags).score)
            losers = [plan for plan in group if plan is not winner]
            for loser in losers:
                loser.skip_execution = True
                loser.skip_reason = f"Conflict: duplicate target kept better source {winner.path.source_path}"
                loser.warnings.append(loser.skip_reason)
            decisions.append(
                ConflictDecision(
                    target_path=target,
                    action="keep-best-source",
                    winner=winner.path.source_path,
                    losers=[loser.path.source_path for loser in losers],
                    reason="duplicate planned target",
                )
            )

        active = [plan for plan in group if not plan.skip_execution]
        if not active:
            continue
        plan = active[0]
        if plan.path.target_path.exists():
            try:
                same_file = os.path.samefile(plan.path.source_path, plan.path.target_path)
            except OSError:
                same_file = False
            if same_file:
                continue
            if policy == "fail":
                plan.errors.append(f"Target already exists: {target}")
                continue
            if policy == "skip":
                plan.skip_execution = True
                plan.skip_reason = f"Conflict: existing target skipped: {target}"
                plan.warnings.append(plan.skip_reason)
                decisions.append(
                    ConflictDecision(
                        target_path=target,
                        action="skip-existing",
                        winner=plan.path.target_path,
                        losers=[plan.path.source_path],
                        reason=plan.skip_reason,
                    )
                )
                continue
            if policy == "suffix":
                plan.path.target_path = _next_available_suffix(plan.path.target_path)
                plan.warnings.append(f"Conflict: existing target renamed to {plan.path.target_path}")
                decisions.append(
                    ConflictDecision(
                        target_path=target,
                        action="suffix-existing",
                        winner=plan.path.source_path,
                        reason="existing target path",
                    )
                )
                continue
            if policy == "replace":
                if not cfg.scan.force_replace:
                    plan.errors.append("Conflict policy 'replace' requires scan.force_replace=true")
                    continue
                plan.replace_existing = True
                plan.warnings.append("Conflict: force replacing existing target")
                decisions.append(
                    ConflictDecision(
                        target_path=target,
                        action="force-replace-existing",
                        winner=plan.path.source_path,
                        losers=[plan.path.target_path],
                        reason="force replace policy",
                    )
                )
                continue
            source_quality = score_candidate(plan.path.source_path, plan.tags.target_tags)
            existing_quality = score_candidate(plan.path.target_path, None, existing_library_file=True)
            if existing_quality.score >= source_quality.score:
                plan.skip_execution = True
                plan.skip_reason = (
                    "Conflict: existing target kept "
                    f"({existing_quality.score:.1f} >= {source_quality.score:.1f})"
                )
                plan.warnings.append(plan.skip_reason)
                decisions.append(
                    ConflictDecision(
                        target_path=target,
                        action="keep-existing",
                        winner=plan.path.target_path,
                        losers=[plan.path.source_path],
                        reason=plan.skip_reason,
                    )
                )
            else:
                plan.replace_existing = True
                warning = (
                    "Conflict: planned source replaces worse existing target "
                    f"({source_quality.score:.1f} > {existing_quality.score:.1f})"
                )
                plan.warnings.append(warning)
                decisions.append(
                    ConflictDecision(
                        target_path=target,
                        action="replace-existing",
                        winner=plan.path.source_path,
                        losers=[plan.path.target_path],
                        reason=warning,
                    )
                )
    return decisions


def _suffix_path(path: Path, index: int) -> Path:
    return path.with_name(f"{path.stem} ({index}){path.suffix}")


def _next_available_suffix(path: Path) -> Path:
    index = 1
    candidate = _suffix_path(path, index)
    while candidate.exists():
        index += 1
        candidate = _suffix_path(path, index)
    return candidate
