import os
from pathlib import Path

import pytest

from kimp3.models import AudioTags, FileOperation
from kimp3.planning import (OperationPlan, PathPlan, PlanValidationError,
                            build_operation_plan, build_path_plan,
                            build_tag_change_plan, render_operation_preview,
                            resolve_operation, resolve_operation_conflicts,
                            score_candidate, validate_audio_plans,
                            validate_operation_plans,
                            validate_pattern_variables)
from kimp3.settings import Settings


class DummySongDir:
    is_compilation = False


def test_external_source_defaults_to_copy(tmp_path):
    settings = Settings.model_validate({"collection": {"directory": str(tmp_path / "library")}})

    operation = resolve_operation(FileOperation.AUTO, tmp_path / "incoming" / "song.mp3", Path(settings.collection.directory))

    assert operation == FileOperation.COPY


def test_source_inside_library_defaults_to_move(tmp_path):
    library = tmp_path / "library"
    settings = Settings.model_validate({"collection": {"directory": str(library)}})

    operation = resolve_operation(FileOperation.AUTO, library / "Artist" / "song.mp3", library)

    assert operation == FileOperation.MOVE


def test_external_move_requires_force(tmp_path):
    with pytest.raises(PlanValidationError):
        resolve_operation(FileOperation.MOVE, tmp_path / "incoming" / "song.mp3", tmp_path / "library")


def test_ext_variable_preserves_source_extension(tmp_path):
    settings = Settings.model_validate(
        {
            "collection": {"directory": str(tmp_path / "library")},
            "paths": {"patterns": {"album": "%album_artist/%song_title.%ext"}},
        }
    )
    tags = AudioTags(title="Track", artist="Artist", album_artist="Artist")

    plan = build_path_plan(tmp_path / "incoming" / "song.mp3", tags, DummySongDir(), settings)

    assert plan.target_path == tmp_path / "library" / "Artist" / "Track.mp3"


def test_conditional_disc_prefix_is_removed_for_single_disc_album(tmp_path):
    settings = Settings.model_validate(
        {
            "collection": {"directory": str(tmp_path / "library")},
            "paths": {
                "patterns": {
                    "album": (
                        "%album_artist/%year - %album_title/"
                        "%?disc_num{%disc_num-}%track_num. %song_title.%ext"
                    )
                }
            },
        }
    )
    tags = AudioTags(
        title="Track",
        artist="Artist",
        album="Album",
        album_artist="Artist",
        track_number=1,
        disc_number=1,
        total_discs=1,
        year=2024,
    )

    plan = build_path_plan(tmp_path / "incoming" / "song.mp3", tags, DummySongDir(), settings)

    assert plan.target_path == (
        tmp_path / "library" / "Artist" / "2024 - Album" / "01. Track.mp3"
    )


def test_conditional_disc_prefix_is_used_for_multi_disc_album(tmp_path):
    settings = Settings.model_validate(
        {
            "collection": {"directory": str(tmp_path / "library")},
            "paths": {
                "patterns": {
                    "album": (
                        "%album_artist/%year - %album_title/"
                        "%?disc_num{%disc_num-}%track_num. %song_title.%ext"
                    )
                }
            },
        }
    )
    tags = AudioTags(
        title="Track",
        artist="Artist",
        album="Album",
        album_artist="Artist",
        track_number=1,
        disc_number=2,
        total_discs=3,
        year=2024,
    )

    plan = build_path_plan(tmp_path / "incoming" / "song.flac", tags, DummySongDir(), settings)

    assert plan.target_path == (
        tmp_path / "library" / "Artist" / "2024 - Album" / "2-01. Track.flac"
    )


def test_conditional_fragment_removes_surrounding_punctuation(tmp_path):
    settings = Settings.model_validate(
        {
            "collection": {"directory": str(tmp_path / "library")},
            "paths": {
                "patterns": {
                    "album": (
                        "%album_artist/%year - %album_title%?disc_num{ (CD%disc_num)}"
                        "/%track_num. %song_title.%ext"
                    )
                }
            },
        }
    )
    tags = AudioTags(
        title="Track",
        artist="Artist",
        album="Album",
        album_artist="Artist",
        track_number=1,
        disc_number=1,
        total_discs=1,
        year=2024,
    )

    plan = build_path_plan(tmp_path / "incoming" / "song.mp3", tags, DummySongDir(), settings)

    assert plan.target_path == (
        tmp_path / "library" / "Artist" / "2024 - Album" / "01. Track.mp3"
    )


def test_unknown_pattern_variable_is_rejected():
    with pytest.raises(PlanValidationError):
        validate_pattern_variables("%artist/%song_title.mp3")


def test_unknown_conditional_pattern_variable_is_rejected():
    with pytest.raises(PlanValidationError):
        validate_pattern_variables("%?artist{%artist - }%song_title.mp3")


def test_duplicate_target_paths_are_detected(tmp_path):
    target = tmp_path / "library" / "same.mp3"
    plans = [
        PathPlan(source_path=tmp_path / "a.mp3", target_path=target, operation=FileOperation.COPY),
        PathPlan(source_path=tmp_path / "b.mp3", target_path=target, operation=FileOperation.COPY),
    ]

    errors = validate_audio_plans(plans)

    assert any("Duplicate target path" in error for error in errors)


def test_flac_backend_is_allowed_in_plan(tmp_path):
    plan = PathPlan(
        source_path=tmp_path / "song.flac",
        target_path=tmp_path / "library" / "song.flac",
        operation=FileOperation.COPY,
    )

    errors = validate_audio_plans([plan])

    assert errors == []


def test_unknown_backend_is_rejected_in_plan(tmp_path):
    plan = PathPlan(
        source_path=tmp_path / "song.ogg",
        target_path=tmp_path / "library" / "song.ogg",
        operation=FileOperation.COPY,
    )

    errors = validate_audio_plans([plan])

    assert any("Unsupported audio backend" in error for error in errors)


def test_tag_change_plan_reports_managed_diffs():
    source = AudioTags(title="Old", artist="Artist", genre="Rock")
    target = AudioTags(title="New", artist="Artist", genre="Rock, Pop")

    plan = build_tag_change_plan(source, target)

    assert plan.requires_write is True
    assert [(change.field, change.old_value, change.new_value) for change in plan.changes] == [
        ("title", "Old", "New"),
        ("genres", ["Rock"], ["Rock", "Pop"]),
    ]


def test_operation_plan_combines_path_and_tag_changes(tmp_path):
    settings = Settings.model_validate(
        {
            "collection": {"directory": str(tmp_path / "library")},
            "paths": {"patterns": {"album": "%album_artist/%song_title.%ext"}},
        }
    )
    source = AudioTags(title="Old", artist="Artist", album_artist="Artist")
    target = AudioTags(title="New", artist="Artist", album_artist="Artist")

    plan = build_operation_plan(tmp_path / "incoming" / "old.mp3", source, target, DummySongDir(), settings)

    assert plan.operation == FileOperation.COPY
    assert plan.path.target_path == tmp_path / "library" / "Artist" / "New.mp3"
    assert plan.requires_tag_write is True
    assert plan.requires_file_operation is True
    assert plan.is_noop is False


def test_path_plan_normalizes_paths_to_absolute(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    plan = PathPlan(
        source_path=Path("incoming/song.mp3"),
        target_path=Path("library/Artist/song.mp3"),
        genre_links=[Path("library/_Genres/Rock/song.mp3")],
        operation=FileOperation.COPY,
    )

    assert plan.source_path == tmp_path / "incoming" / "song.mp3"
    assert plan.target_path == tmp_path / "library" / "Artist" / "song.mp3"
    assert plan.genre_links == [
        tmp_path / "library" / "_Genres" / "Rock" / "song.mp3"
    ]


def test_path_plan_keeps_existing_symlink_path(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "library" / "Artist" / "song.mp3"
    link = tmp_path / "library" / "_Genres" / "Rock" / "song.mp3"
    target.parent.mkdir(parents=True)
    link.parent.mkdir(parents=True)
    target.write_bytes(b"audio")
    link.symlink_to(os.path.relpath(target, link.parent))

    plan = PathPlan(
        source_path=Path("incoming/song.mp3"),
        target_path=target,
        genre_links=[link],
        operation=FileOperation.COPY,
    )

    assert plan.genre_links == [link]
    assert plan.genre_links[0].resolve() == target


def test_operation_plan_noop_for_matching_tags_and_path(tmp_path):
    library = tmp_path / "library"
    settings = Settings.model_validate(
        {
            "collection": {"directory": str(library), "create_genre_links": False},
            "paths": {"patterns": {"album": "%album_artist/%song_title.%ext"}},
        }
    )
    tags = AudioTags(title="song", artist="Artist", album_artist="Artist")
    source_path = library / "Artist" / "song.mp3"

    plan = build_operation_plan(source_path, tags, tags, DummySongDir(), settings)

    assert plan.operation == FileOperation.MOVE
    assert plan.requires_tag_write is False
    assert plan.requires_file_operation is False
    assert plan.is_noop is True


def test_score_candidate_prefers_flac_over_mp3(tmp_path):
    mp3 = tmp_path / "song.mp3"
    flac = tmp_path / "song.flac"
    mp3.write_bytes(b"x" * 1024)
    flac.write_bytes(b"x" * 1024)

    assert score_candidate(flac).score > score_candidate(mp3).score


def test_duplicate_target_keeps_best_source(tmp_path):
    target = tmp_path / "library" / "Artist" / "song.flac"
    source_mp3 = tmp_path / "incoming" / "song.mp3"
    source_flac = tmp_path / "incoming" / "song.flac"
    source_mp3.parent.mkdir()
    source_mp3.write_bytes(b"mp3")
    source_flac.write_bytes(b"flac")
    target_tags = AudioTags(title="Song", artist="Artist")
    plans = [
        OperationPlan(
            path=PathPlan(source_path=source_mp3, target_path=target, operation=FileOperation.COPY),
            tags=build_tag_change_plan(AudioTags(title="Song", artist="Artist"), target_tags),
        ),
        OperationPlan(
            path=PathPlan(source_path=source_flac, target_path=target, operation=FileOperation.COPY),
            tags=build_tag_change_plan(AudioTags(title="Song", artist="Artist"), target_tags),
        ),
    ]

    decisions = resolve_operation_conflicts(plans)

    assert decisions[0].action == "keep-best-source"
    assert plans[0].skip_execution is True
    assert plans[1].skip_execution is False


def test_existing_target_kept_when_not_worse(tmp_path):
    source = tmp_path / "incoming" / "song.mp3"
    target = tmp_path / "library" / "Artist" / "song.mp3"
    source.parent.mkdir()
    target.parent.mkdir(parents=True)
    source.write_bytes(b"x")
    target.write_bytes(b"x" * 4096)
    settings = Settings.model_validate(
        {
            "collection": {"directory": str(tmp_path / "library")},
            "paths": {"patterns": {"album": "%album_artist/%song_title.%ext"}},
        }
    )
    plan = build_operation_plan(source, AudioTags(), AudioTags(title="song", album_artist="Artist"), DummySongDir(), settings)

    resolve_operation_conflicts([plan])

    assert plan.skip_execution is True
    assert plan.replace_existing is False


def test_existing_target_replaced_when_source_is_better(tmp_path):
    source = tmp_path / "incoming" / "song.flac"
    target = tmp_path / "library" / "Artist" / "song.flac"
    source.parent.mkdir()
    target.parent.mkdir(parents=True)
    source.write_bytes(b"x" * 4096)
    target.write_bytes(b"x")
    settings = Settings.model_validate(
        {
            "collection": {"directory": str(tmp_path / "library")},
            "paths": {"patterns": {"album": "%album_artist/%song_title.%ext"}},
        }
    )
    plan = build_operation_plan(
        source,
        AudioTags(),
        AudioTags(title="song", album_artist="Artist", artist="Artist", album="Album", year=2024, genre="Rock"),
        DummySongDir(),
        settings,
    )

    resolve_operation_conflicts([plan])

    assert plan.skip_execution is False
    assert plan.replace_existing is True


def test_conflict_policy_fail_marks_existing_target_error(monkeypatch, tmp_path):
    monkeypatch.setattr("kimp3.config.cfg.scan.conflict_policy", "fail")
    source = tmp_path / "incoming" / "song.mp3"
    target = tmp_path / "library" / "Artist" / "song.mp3"
    source.parent.mkdir()
    target.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    target.write_bytes(b"target")
    plan = OperationPlan(
        path=PathPlan(source_path=source, target_path=target, operation=FileOperation.COPY),
        tags=build_tag_change_plan(AudioTags(title="Source"), AudioTags(title="Target")),
    )

    resolve_operation_conflicts([plan])

    assert any("Target already exists" in error for error in plan.errors)


def test_conflict_policy_replace_requires_force(monkeypatch, tmp_path):
    monkeypatch.setattr("kimp3.config.cfg.scan.conflict_policy", "replace")
    monkeypatch.setattr("kimp3.config.cfg.scan.force_replace", False)
    source = tmp_path / "incoming" / "song.mp3"
    target = tmp_path / "library" / "Artist" / "song.mp3"
    source.parent.mkdir()
    target.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    target.write_bytes(b"target")
    plan = OperationPlan(
        path=PathPlan(source_path=source, target_path=target, operation=FileOperation.COPY),
        tags=build_tag_change_plan(AudioTags(title="Source"), AudioTags(title="Target")),
    )

    resolve_operation_conflicts([plan])

    assert any("force_replace" in error for error in plan.errors)


def test_conflict_policy_replace_with_force_sets_replace(monkeypatch, tmp_path):
    monkeypatch.setattr("kimp3.config.cfg.scan.conflict_policy", "replace")
    monkeypatch.setattr("kimp3.config.cfg.scan.force_replace", True)
    source = tmp_path / "incoming" / "song.mp3"
    target = tmp_path / "library" / "Artist" / "song.mp3"
    source.parent.mkdir()
    target.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    target.write_bytes(b"target")
    plan = OperationPlan(
        path=PathPlan(source_path=source, target_path=target, operation=FileOperation.COPY),
        tags=build_tag_change_plan(AudioTags(title="Source"), AudioTags(title="Target")),
    )

    resolve_operation_conflicts([plan])

    assert plan.errors == []
    assert plan.replace_existing is True


def test_conflict_policy_suffix_renames_existing_target(monkeypatch, tmp_path):
    monkeypatch.setattr("kimp3.config.cfg.scan.conflict_policy", "suffix")
    source = tmp_path / "incoming" / "song.mp3"
    target = tmp_path / "library" / "Artist" / "song.mp3"
    source.parent.mkdir()
    target.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    target.write_bytes(b"target")
    plan = OperationPlan(
        path=PathPlan(source_path=source, target_path=target, operation=FileOperation.COPY),
        tags=build_tag_change_plan(AudioTags(title="Source"), AudioTags(title="Target")),
    )

    resolve_operation_conflicts([plan])

    assert plan.path.target_path.name == "song (1).mp3"


def test_validate_audio_plans_rejects_self_referential_genre_link(monkeypatch, tmp_path):
    library = tmp_path / "library"
    target = library / "Artist" / "song.mp3"
    source = tmp_path / "incoming" / "song.mp3"
    monkeypatch.setattr("kimp3.config.cfg.collection.directory", str(library))
    monkeypatch.setattr(
        "kimp3.config.cfg.paths.patterns.genre", "_Genres/%genre/%song_title.mp3"
    )
    plan = PathPlan(
        source_path=source,
        target_path=target,
        genre_links=[target],
        operation=FileOperation.COPY,
    )

    errors = validate_audio_plans([plan])

    assert any("Genre symlink points to itself" in error for error in errors)
    assert any("Genre symlink outside genre directory" in error for error in errors)


def test_validate_audio_plans_rejects_genre_link_outside_genre_root(monkeypatch, tmp_path):
    library = tmp_path / "library"
    source = tmp_path / "incoming" / "song.mp3"
    target = library / "Artist" / "song.mp3"
    bad_link = library / "Artist" / "by-genre.mp3"
    monkeypatch.setattr("kimp3.config.cfg.collection.directory", str(library))
    monkeypatch.setattr(
        "kimp3.config.cfg.paths.patterns.genre", "_Genres/%genre/%song_title.mp3"
    )
    plan = PathPlan(
        source_path=source,
        target_path=target,
        genre_links=[bad_link],
        operation=FileOperation.COPY,
    )

    errors = validate_audio_plans([plan])

    assert errors == [f"Genre symlink outside genre directory: {bad_link}"]


def test_validate_operation_plans_rejects_self_referential_genre_link(
    monkeypatch, tmp_path
):
    library = tmp_path / "library"
    target = library / "Artist" / "song.mp3"
    source = tmp_path / "incoming" / "song.mp3"
    monkeypatch.setattr("kimp3.config.cfg.collection.directory", str(library))
    monkeypatch.setattr(
        "kimp3.config.cfg.paths.patterns.genre", "_Genres/%genre/%song_title.mp3"
    )
    plan = OperationPlan(
        path=PathPlan(
            source_path=source,
            target_path=target,
            genre_links=[target],
            operation=FileOperation.COPY,
        ),
        tags=build_tag_change_plan(AudioTags(), AudioTags()),
    )

    errors = validate_operation_plans([plan])

    assert any("Genre symlink points to itself" in error for error in errors)


def test_build_path_plan_rejects_album_pattern_as_genre_pattern(tmp_path):
    settings = Settings.model_validate(
        {
            "collection": {
                "directory": str(tmp_path / "library"),
                "create_genre_links": True,
            },
            "paths": {
                "patterns": {
                    "album": "%album_artist/%year - %album_title/%track_num. %song_title.%ext",
                    "genre": "%album_artist/%year - %album_title/%track_num. %song_title.%ext",
                }
            },
        }
    )
    tags = AudioTags(
        title="Song",
        artist="Artist",
        album="Album",
        album_artist="Artist",
        track_number=1,
        year=2024,
        genres=["Rock"],
    )

    with pytest.raises(PlanValidationError, match="Genre symlink points to itself"):
        build_path_plan(tmp_path / "incoming" / "song.mp3", tags, DummySongDir(), settings)


def test_render_operation_preview_contains_tags_paths_and_links(tmp_path):
    plan = OperationPlan(
        path=PathPlan(
            source_path=tmp_path / "source.mp3",
            target_path=tmp_path / "library" / "song.mp3",
            genre_links=[tmp_path / "library" / "_Genres" / "Rock" / "song.mp3"],
            operation=FileOperation.COPY,
        ),
        tags=build_tag_change_plan(AudioTags(title="Old"), AudioTags(title="New")),
    )

    preview = "\n".join(render_operation_preview(plan))

    assert "operation: copy" in preview
    assert "title: 'Old' -> 'New'" in preview
    assert "genre symlinks:" in preview
