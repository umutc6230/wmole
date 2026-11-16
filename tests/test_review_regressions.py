"""Regression tests for the November 2026 data-safety review. Fixtures only."""

import json
import os
import threading
from pathlib import Path
from unittest import mock

import pytest

import mole


@pytest.fixture
def vault(tmp_path, monkeypatch):
    home = tmp_path / "state"
    monkeypatch.setattr(mole, "WMOLE_DIR", home)
    names = {
        "CONFIG_FILE": "config.json",
        "WHITELIST_FILE": "whitelist.txt",
        "DENYLIST_FILE": "denylist.txt",
        "PURGE_PATHS_FILE": "purge_paths.txt",
        "CACHE_FILE": "cache.json",
        "COMPLETION_FILE": "completion.ps1",
        "QUARANTINE_DIR": "quarantine",
        "QUARANTINE_INDEX": "quarantine/index.json",
        "JOURNAL_DB": "journal.db",
        "SECURITY_KEY_FILE": "security.key",
        "SECURITY_LOG_FILE": "security.jsonl",
        "OP_LOG_FILE": "operations.log",
    }
    for name, relative in names.items():
        monkeypatch.setattr(mole, name, home / relative)
    monkeypatch.setattr(mole, "JOURNAL", mole.OperationJournal(home / "journal.db"))
    monkeypatch.setattr(mole, "load_whitelist", lambda: [])
    monkeypatch.setattr(mole, "load_denylist", lambda: [])
    monkeypatch.setattr(mole, "git_delete_risk", lambda p: "")
    monkeypatch.setattr(mole, "load_config", lambda: {"quarantine_enabled": True})
    return home


def old(path):
    stamp = mole.time.time() - 3 * 86400
    os.utime(path, (stamp, stamp))
    return path


@pytest.mark.parametrize("trash", [False, True])
@pytest.mark.parametrize("list_name", ["load_whitelist", "load_denylist"])
def test_protected_descendant_blocks_entire_tree_before_changes(
    vault, tmp_path, monkeypatch, trash, list_name
):
    root = tmp_path / "parent"
    root.mkdir()
    keep = root / "keep.txt"
    keep.write_text("important")
    sibling = root / "other.txt"
    sibling.write_text("also intact")
    monkeypatch.setattr(mole, list_name, lambda: [keep])
    assert mole.delete_path(root, trash, False)
    assert keep.read_text() == "important"
    assert sibling.exists()
    assert not mole._quarantine_entries()


@pytest.mark.parametrize("trash", [False, True])
def test_temp_root_cannot_bypass_denylist(vault, tmp_path, monkeypatch, trash):
    root = tmp_path / "Temp"
    root.mkdir()
    target = root / "keep.txt"
    target.write_text("important")
    old(target)
    monkeypatch.setattr(mole, "TEMP", root)
    monkeypatch.setattr(mole, "load_denylist", lambda: [root])
    assert mole.delete_path(root, trash, False)
    assert target.exists()


def test_temp_is_reversible_and_restores_exact_content(vault, tmp_path, monkeypatch):
    root = tmp_path / "Temp"
    root.mkdir()
    target = root / "old.txt"
    target.write_bytes(b"must survive")
    old(target)
    monkeypatch.setattr(mole, "TEMP", root)
    report = {}
    assert mole.delete_path(root, True, False, report=report) is None
    assert root.is_dir() and not target.exists()
    assert report["bytes"] == 0 and report["removed"] == 1
    entry = mole._quarantine_entries()[0]
    assert mole.restore_quarantine(entry["id"]) is None
    assert target.read_bytes() == b"must survive"


def test_old_directory_with_new_descendant_is_preserved(vault, tmp_path, monkeypatch):
    root = tmp_path / "Temp"
    folder = root / "old-dir"
    folder.mkdir(parents=True)
    fresh = folder / "new.txt"
    fresh.write_text("fresh")
    old(folder)
    monkeypatch.setattr(mole, "TEMP", root)
    report = {}
    assert mole.delete_path(root, False, False, report=report) is None
    assert fresh.exists()
    assert report["removed"] == 0 and report["skipped"] == 1
    assert not report["completed"] and report["bytes"] == 0


def test_temp_respects_protected_child_and_still_cleans_safe_sibling(vault, tmp_path, monkeypatch):
    root = tmp_path / "Temp"
    root.mkdir()
    keep, remove = root / "keep", root / "remove"
    for path in (keep, remove):
        path.write_text("fixture")
        old(path)
    monkeypatch.setattr(mole, "TEMP", root)
    monkeypatch.setattr(mole, "load_whitelist", lambda: [keep])
    report = {}
    assert mole.delete_path(root, False, False, report=report) is None
    assert keep.exists() and not remove.exists()
    assert report["skipped"] == 1 and report["removed"] == 1


@pytest.mark.parametrize("expire", [False, True])
def test_failed_vault_removal_keeps_restore_index(vault, tmp_path, monkeypatch, expire):
    source = tmp_path / "source"
    source.write_text("data")
    assert mole.quarantine_path(source, 4) is None
    entries = mole._quarantine_entries()
    entries[0]["created"] = 1
    mole._save_quarantine_entries(entries)
    monkeypatch.setattr(mole.shutil, "rmtree", lambda *a, **kw: None)
    if expire:
        assert mole.purge_expired_quarantine() == 0
    else:
        assert mole.empty_quarantine() == {"removed": 0, "bytes": 0, "failed": 1}
    assert mole._quarantine_entries() == entries
    assert Path(entries[0]["stored"]).exists()


def test_reset_keeps_quarantine_journal_security_and_unknown_files(vault):
    vault.mkdir()
    for path in (
        mole.CONFIG_FILE,
        mole.CACHE_FILE,
        mole.SECURITY_KEY_FILE,
        mole.JOURNAL_DB,
        vault / "user-backup.txt",
    ):
        path.write_text("fixture")
    mole.QUARANTINE_DIR.mkdir()
    stored = mole.QUARANTINE_DIR / "keep.txt"
    stored.write_text("recover me")
    # This test isolates reset selection from the live journal connection.
    with mock.patch.object(mole, "JOURNAL"):
        result = {}
        mole.cli_remove(False, False, result)
    assert all(row["result"] == "ok" for row in result["results"])
    assert not mole.CONFIG_FILE.exists() and not mole.CACHE_FILE.exists()
    assert stored.read_text() == "recover me"
    assert mole.SECURITY_KEY_FILE.exists() and mole.JOURNAL_DB.exists()
    assert (vault / "user-backup.txt").exists()


def test_yes_clean_never_reads_stdin_and_records_run(vault, monkeypatch):
    scanner = mock.Mock(categories=[])
    monkeypatch.setattr(mole, "Scanner", lambda **kw: scanner)
    monkeypatch.setattr("builtins.input", mock.Mock(side_effect=AssertionError("stdin used")))
    mole.cli_clean(False, False, yes=True)
    result = json.loads((vault / "last_scheduled_cleanup.json").read_text())
    assert result["ok"] == 0 and result["errors"] == 0


def test_main_passes_yes_to_clean(monkeypatch):
    monkeypatch.setattr(mole.sys, "argv", ["wmole", "clean", "--yes"])
    monkeypatch.setattr(mole, "start_auto_update_check", lambda: None)
    monkeypatch.setattr(mole, "purge_expired_quarantine", lambda: 0)
    with mock.patch.object(mole, "cli_clean") as clean:
        mole.main_cli()
    assert clean.call_args.kwargs["yes"] is True


def test_source_update_preview_never_runs_commands(monkeypatch):
    monkeypatch.delattr(mole.sys, "frozen", raising=False)
    with mock.patch.object(mole.subprocess, "run", side_effect=AssertionError("mutation")):
        mole.cli_update(False, dry_run=True, quiet=True)


def test_checksum_only_cli_update_never_executes(tmp_path):
    with mock.patch.object(mole.subprocess, "Popen") as launch:
        with pytest.raises(RuntimeError, match="disabled"):
            mole._launch_updated(tmp_path / "payload.exe", "payload.exe", "v99")
        launch.assert_not_called()


def test_concurrent_mutation_is_rejected_without_deleting(monkeypatch):
    events = []
    with mole._MUTATION_LOCK, mock.patch.object(mole, "_serve_delete") as delete:
        mole._serve_handle({"id": "second", "op": "delete"}, events.append, {})
    delete.assert_not_called()
    assert events[-1]["ok"] is False


def test_delete_events_keep_skipped_temp_row(vault, tmp_path, monkeypatch):
    root = tmp_path / "Temp"
    root.mkdir()
    (root / "new.txt").write_text("new")
    monkeypatch.setattr(mole, "TEMP", root)
    events = []
    mole._serve_delete({"id": "test", "targets": [str(root)]}, events.append, threading.Event())
    item = next(e for e in events if e["ev"] == "item_result")
    assert not item["completed"]
    assert item["report"]["skipped"] == 1 and item["trashed"] is True


def test_batch_delete_cannot_bypass_whitelist(vault, tmp_path, monkeypatch):
    target = tmp_path / "keep.txt"
    target.write_text("fixture")
    monkeypatch.setattr(mole, "load_whitelist", lambda: [target])
    assert mole.trash_paths_batch([target])[str(target)]
    assert target.exists()
