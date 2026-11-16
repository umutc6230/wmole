import json
import io
import contextlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import mole
from rich.console import Console


class WmoleBehaviorTests(unittest.TestCase):
    def test_read_cleanup_history_sums_only_successful_deletions(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "operations.log"
            log.write_text(
                "2026-05-29 10:00:00\tdelete-trash\t100\tC:\\a\\cache\tok\n"
                "2026-05-29 10:01:00\tdelete-permanent\t50\tC:\\b\\tmp\tok\n"
                "2026-05-29 10:02:00\tdelete-dry-run\t999\tC:\\c\\x\tok\n"
                "2026-05-29 10:03:00\tdelete-trash\t7\tC:\\d\\y\ttrash: failed\n"
                "2026-05-29 10:04:00\tdelete-blocked\t30\tC:\\Windows\tprotected path\n",
                encoding="utf-8",
            )
            with mock.patch.object(mole, "OP_LOG_FILE", log):
                hist = mole.read_cleanup_history(limit=5)
            self.assertEqual(hist["count"], 2)
            self.assertEqual(hist["total_freed"], 50)  # recycle-bin moves do not free space
            self.assertEqual(hist["last_ts"], "2026-05-29 10:01:00")
            # newest-first ordering
            self.assertEqual(hist["recent"][0]["path"], "C:\\b\\tmp")

    def test_trash_paths_batch_sends_all_paths_in_one_call(self):
        calls = []

        def fake_send2trash(arg):
            calls.append(arg)

        paths = [Path(r"C:\a\cache"), Path(r"C:\b\tmp")]
        with (
            mock.patch.object(mole, "send2trash", fake_send2trash),
            mock.patch.object(mole, "load_config", return_value={"quarantine_enabled": False}),
        ):
            res = mole.trash_paths_batch(paths, sizes={str(paths[0]): 100, str(paths[1]): 5})

        # One batched call carrying both paths as a list.
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], [str(paths[0]), str(paths[1])])
        self.assertEqual(res[str(paths[0])], None)
        self.assertEqual(res[str(paths[1])], None)

    def test_trash_paths_batch_falls_back_per_path_on_batch_failure(self):
        attempts = []

        def fake_send2trash(arg):
            attempts.append(arg)
            if isinstance(arg, list):
                raise OSError("batch boom")
            if arg.endswith("bad"):
                raise OSError("nope")

        paths = [Path(r"C:\good"), Path(r"C:\bad")]
        with (
            mock.patch.object(mole, "send2trash", fake_send2trash),
            mock.patch.object(mole, "load_config", return_value={"quarantine_enabled": False}),
        ):
            res = mole.trash_paths_batch(paths)

        self.assertIsNone(res[str(paths[0])])
        self.assertIn("trash:", res[str(paths[1])])

    def test_render_dashboard_handles_missing_scanner(self):
        with mock.patch.object(mole, "OP_LOG_FILE", Path("does-not-exist.log")):
            group = mole.render_dashboard(scanner=None)
        self.assertIsNotNone(group)

    def test_analyze_path_entries_reports_children_and_large_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "small.txt").write_bytes(b"a" * 10)
            nested = root / "nested"
            nested.mkdir()
            (nested / "big.bin").write_bytes(b"b" * 2048)

            result = mole.analyze_path(root, large_file_min=1024)

            self.assertEqual(result["path"], str(root))
            self.assertEqual(result["total_files"], 2)
            self.assertEqual(result["total_size"], 2058)
            self.assertEqual(result["entries"][0]["name"], "nested")
            self.assertEqual(result["entries"][0]["size"], 2048)
            self.assertEqual(result["large_files"][0]["name"], "big.bin")
            json.dumps(result)

    def test_purge_candidates_only_include_known_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            keep = root / "src"
            keep.mkdir()
            artifact = root / "app" / "node_modules"
            artifact.mkdir(parents=True)
            (artifact / "pkg.txt").write_bytes(b"x" * 3)

            categories = mole.build_purge_categories([root], whitelist=[])

            paths = [item.path for cat in categories for item in cat.items]
            self.assertIn(artifact, paths)
            self.assertNotIn(keep, paths)

    def test_protected_path_blocks_drive_root_and_windows_dir(self):
        self.assertTrue(mole.is_protected_path(Path("C:\\")))
        self.assertTrue(mole.is_protected_path(Path(r"C:\Windows\System32")))
        self.assertFalse(
            mole.is_protected_path(Path(r"C:\Users\example\AppData\Local\Temp\wmole-safe"))
        )

    def test_installer_categories_are_separate_from_full_scanner(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            installer = root / "setup.exe"
            installer.write_bytes(b"x" * 7)

            categories = mole.build_installer_categories([root], days=0)

            self.assertEqual(len(categories), 1)
            self.assertEqual(categories[0].key, "installers")
            self.assertEqual(categories[0].items[0].path, installer)
            self.assertEqual(categories[0].items[0].size, 7)

    def test_fixed_categories_include_common_windows_app_caches(self):
        keys = {row[0] for row in mole.build_fixed_path_categories()}

        self.assertIn("firefox-cache", keys)
        self.assertIn("brave-cache", keys)
        self.assertIn("discord-cache", keys)
        self.assertIn("teams-cache", keys)
        self.assertIn("thumbnail-cache", keys)
        self.assertIn("directx-shader-cache", keys)
        self.assertIn("store-cache", keys)
        self.assertIn("wsl-logs", keys)

    def test_configured_purge_roots_override_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            config_root = home / "custom-work"
            config_root.mkdir()
            paths_file = home / ".wmole" / "purge_paths.txt"
            paths_file.parent.mkdir()
            paths_file.write_text("# comment\n~/custom-work\n\n", encoding="utf-8")

            roots = mole.load_purge_roots(home=home)

            self.assertEqual(roots, [config_root])

    def test_firefox_fixed_category_targets_cache2_not_profile_root(self):
        with tempfile.TemporaryDirectory() as td:
            profiles = Path(td) / "Profiles"
            cache = profiles / "abc.default" / "cache2"
            cache.mkdir(parents=True)

            items = mole.fixed_category_items("firefox-cache", profiles, selected=True)

            self.assertEqual([item.path for item in items], [cache])

    def test_fixed_category_items_skips_inaccessible_path(self):
        blocked = Path(r"C:\blocked-cache")
        with mock.patch.object(Path, "exists", side_effect=PermissionError("denied")):
            items = mole.fixed_category_items("delivery-optimization", blocked, selected=True)

        self.assertEqual(items, [])

    def test_clean_scanner_does_not_scan_dev_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "project" / "node_modules"
            artifact.mkdir(parents=True)
            (artifact / "pkg.txt").write_bytes(b"x" * 5)

            scanner = mole.Scanner(whitelist=[], profile="clean", roots=[root])
            scanner.run()

            keys = {cat.key for cat in scanner.categories}
            self.assertNotIn("dev-node_modules", keys)

    def test_purge_scanner_only_builds_purge_categories(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "project" / "node_modules"
            artifact.mkdir(parents=True)
            (artifact / "pkg.txt").write_bytes(b"x" * 5)

            scanner = mole.Scanner(whitelist=[], profile="purge", roots=[root])
            scanner.run()

            self.assertEqual([cat.key for cat in scanner.categories], ["dev-node_modules"])

    def test_leftover_matching_normalizes_app_names_and_includes_shortcuts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            appdata = root / "Local"
            shortcuts = root / "Start Menu"
            target = appdata / "FooBar"
            shortcut = shortcuts / "Foo Bar.lnk"
            target.mkdir(parents=True)
            shortcuts.mkdir()
            shortcut.write_bytes(b"shortcut")

            app = {"name": "Foo Bar 2024 (x64)", "publisher": "Foo Inc."}
            items = mole.find_leftover_candidates(app, roots=[appdata, shortcuts])

            paths = {item.path for item in items}
            self.assertIn(target, paths)
            self.assertIn(shortcut, paths)

    def test_collect_selected_targets_separates_protected_items(self):
        allowed = mole.Item(
            path=Path(r"C:\Users\example\AppData\Local\Temp\cache"), size=10, selected=True
        )
        blocked = mole.Item(path=Path(r"C:\Windows\System32"), size=20, selected=True)
        cat = mole.Category(key="test", title="Test", description="", items=[allowed, blocked])

        result = mole.collect_selected_targets([cat], estimated=True)

        self.assertEqual([row["path"] for row in result["targets"]], [str(allowed.path)])
        self.assertEqual(result["total"], 10)
        self.assertEqual(result["blocked"][0]["path"], str(blocked.path))
        self.assertTrue(result["estimated"])

    def test_filter_apps_supports_query_and_limit(self):
        apps = [
            {"name": "Zoom Workplace", "publisher": "Zoom"},
            {"name": "Git", "publisher": "The Git Development Community"},
            {"name": "Google Chrome", "publisher": "Google"},
        ]

        filtered = mole.filter_apps(apps, query="git", limit=1)

        self.assertEqual(filtered, [apps[1]])

    def test_palette_exposes_operations_and_existing_context_actions(self):
        with mock.patch.object(mole, "LANG", "en"):
            names = [cmd["name"] for cmd in mole.palette_commands()]

        self.assertEqual(
            names,
            [
                "dashboard",
                "analyze",
                "categories",
                "clean",
                "purge",
                "installers",
                "uninstall",
                "optimize",
                "status",
                "ports",
                "update",
                "help",
                "doctor",
                "undo",
                "hook",
                "large",
                "drives",
                "select",
                "delete",
                "permanent",
                "open",
                "refresh",
                "leftovers",
                "lang",
                "back",
                "quit",
            ],
        )
        self.assertEqual(mole.filter_palette("/permanent")[0]["action"], "key:k")
        self.assertEqual(mole.filter_palette("/quit")[0]["action"], "exec:quit")

    def test_palette_can_render_selection_beyond_first_page(self):
        output = io.StringIO()
        test_console = Console(record=True, width=120, color_system=None, file=output)
        with mock.patch.object(mole, "LANG", "en"):
            last_index = len(mole.palette_commands()) - 1
            test_console.print(mole.render_palette("", last_index))

        rendered = test_console.export_text()
        self.assertIn("/quit", rendered)
        self.assertIn("> /quit", rendered)
        self.assertNotIn("/analyze", rendered)

    def test_enter_runs_highlighted_palette_command_after_scrolling(self):
        keys = iter(["/"] + ["DOWN"] * (len(mole.palette_commands()) - 1) + ["ENTER"])
        fake_scanner = mock.Mock(
            status="",
            done=True,
            current_cat_key=None,
            current_item_id=None,
        )
        fake_live = mock.MagicMock()
        fake_live.__enter__.return_value = fake_live
        fake_live.__exit__.return_value = False
        empty_category = mole.Category(
            key="fs:test", title=r"C:\Users\example", description="", items=[]
        )
        with (
            mock.patch.object(mole, "Scanner", return_value=fake_scanner),
            mock.patch.object(mole.threading, "Thread") as thread,
            mock.patch.object(mole, "Live", return_value=fake_live),
            mock.patch.object(mole, "build_fs_category", return_value=empty_category),
            mock.patch.object(mole, "load_whitelist", return_value=[]),
            mock.patch.object(mole, "load_config", return_value={"quick_clean_v2_done": True}),
            mock.patch.object(mole, "free_space_gb", return_value=18.1),
            mock.patch.object(mole.os, "system"),
            mock.patch.object(mole.msvcrt, "kbhit", return_value=True),
            mock.patch.object(mole, "read_key", side_effect=lambda: next(keys)),
        ):
            mole.run_tui()

        thread.return_value.start.assert_called_once()

    def test_command_input_is_visible_when_palette_is_idle(self):
        output = io.StringIO()
        console = Console(record=True, width=100, color_system=None, file=output)
        with mock.patch.object(mole, "LANG", "en"):
            console.print(mole.render_command_input())

        rendered = console.export_text()
        self.assertIn("Type / to open operations", rendered)

    def test_help_and_footer_do_not_advertise_top_level_mode_hotkeys(self):
        with mock.patch.object(mole, "LANG", "en"):
            help_text = "\n".join(line for _, lines in mole._help_sections_en() for line in lines)
            footer_text = "\n".join(mole.build_footer_lines(160))

        self.assertIn("/analyze", help_text)
        self.assertNotIn("Shift+A", help_text)
        self.assertNotIn("A Analyze(FS)", footer_text)

    def test_open_palette_places_command_rows_within_visible_terminal_height(self):
        output = io.StringIO()
        test_console = Console(record=True, width=140, height=40, color_system=None, file=output)
        items = [
            mole.Item(path=Path(rf"C:\Users\example\folder-{index}"), size=index + 1)
            for index in range(30)
        ]
        category = mole.Category(
            key="fs:test",
            title=r"C:\Users\example",
            description="",
            items=items,
            scanning=False,
        )
        scanner = mock.Mock(
            status="",
            done=True,
            current_cat_key=None,
            current_item_id=None,
        )
        view = mole.View(title=category.title, kind="items", category=category)

        with (
            mock.patch.object(mole, "console", test_console),
            mock.patch.object(mole, "LANG", "en"),
            mock.patch.object(mole, "free_space_gb", return_value=18.1),
        ):
            test_console.print(
                mole.render(scanner, view, 0, "", True, False, [], [], palette=("", 0))
            )

        lines = test_console.export_text().splitlines()
        first_command_row = next(
            (index for index, line in enumerate(lines) if "/analyze" in line),
            None,
        )
        last_command_row = next(
            (index for index, line in enumerate(lines) if "/help" in line),
            None,
        )
        self.assertIsNotNone(first_command_row)
        self.assertIsNotNone(last_command_row)
        self.assertLess(first_command_row, test_console.height)
        self.assertLess(last_command_row, test_console.height)
        self.assertLessEqual(len(lines), test_console.height)

    def test_open_palette_scrolls_inside_border_in_short_terminal(self):
        output = io.StringIO()
        test_console = Console(record=True, width=140, height=30, color_system=None, file=output)
        items = [
            mole.Item(path=Path(rf"C:\Users\example\folder-{index}"), size=index + 1)
            for index in range(30)
        ]
        category = mole.Category(
            key="fs:test",
            title=r"C:\Users\example",
            description="",
            items=items,
            scanning=False,
        )
        scanner = mock.Mock(
            status="",
            done=True,
            current_cat_key=None,
            current_item_id=None,
        )
        view = mole.View(title=category.title, kind="items", category=category)
        with (
            mock.patch.object(mole, "console", test_console),
            mock.patch.object(mole, "LANG", "en"),
            mock.patch.object(mole, "free_space_gb", return_value=18.1),
        ):
            test_console.print(
                mole.render(
                    scanner,
                    view,
                    0,
                    "",
                    True,
                    False,
                    [],
                    [],
                    palette=("", len(mole.palette_commands()) - 1),
                )
            )

        lines = test_console.export_text().splitlines()
        self.assertIn("/quit", "\n".join(lines))
        self.assertLessEqual(len(lines), test_console.height)
        self.assertTrue(lines[-1].startswith("\u2514"))

    def test_open_palette_prioritizes_closed_frame_in_minimal_terminal(self):
        output = io.StringIO()
        test_console = Console(record=True, width=140, height=22, color_system=None, file=output)
        items = [
            mole.Item(path=Path(rf"C:\Users\example\folder-{index}"), size=index + 1)
            for index in range(30)
        ]
        category = mole.Category(
            key="fs:test",
            title=r"C:\Users\example",
            description="",
            items=items,
            scanning=False,
        )
        scanner = mock.Mock(
            status="",
            done=True,
            current_cat_key=None,
            current_item_id=None,
        )
        view = mole.View(title=category.title, kind="items", category=category)
        with (
            mock.patch.object(mole, "console", test_console),
            mock.patch.object(mole, "LANG", "en"),
            mock.patch.object(mole, "free_space_gb", return_value=18.1),
        ):
            test_console.print(
                mole.render(
                    scanner,
                    view,
                    0,
                    "",
                    True,
                    False,
                    [],
                    [],
                    palette=("", len(mole.palette_commands()) - 1),
                )
            )

        lines = test_console.export_text().splitlines()
        self.assertIn("> /quit", "\n".join(lines))
        self.assertLessEqual(len(lines), test_console.height)
        self.assertTrue(lines[-1].startswith("\u2514"))

    def test_quiet_update_check_returns_visible_up_to_date_status(self):
        release = {"tag_name": f"v{mole.__version__}", "assets": []}
        stdout = io.StringIO()
        with (
            mock.patch.object(mole.sys, "frozen", True, create=True),
            mock.patch.object(mole, "fetch_latest_release", return_value=release),
            contextlib.redirect_stdout(stdout),
        ):
            status = mole.cli_update(json_out=False, quiet=True)

        self.assertEqual(status, "already up to date")
        self.assertEqual(stdout.getvalue(), "")

    def test_turkish_tui_update_status_explicitly_reports_current_version(self):
        with mock.patch.object(mole, "LANG", "tr"):
            self.assertEqual(
                mole.format_tui_update_status("already up to date"),
                "Sürüm güncel.",
            )

    def test_disabling_auto_update_does_not_start_background_check(self):
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / ".wmole"
            config_file = state_dir / "config.json"
            stdout = io.StringIO()
            with (
                mock.patch("sys.argv", ["wmole", "update", "--disable-auto", "--json"]),
                mock.patch.object(mole, "WMOLE_DIR", state_dir),
                mock.patch.object(mole, "CONFIG_FILE", config_file),
                mock.patch.object(mole, "load_config", return_value={}),
                mock.patch.object(mole, "load_whitelist", return_value=[]),
                mock.patch.object(mole, "start_auto_update_check") as start_check,
                contextlib.redirect_stdout(stdout),
            ):
                mole.main_cli()

        start_check.assert_not_called()
        self.assertFalse(json.loads(stdout.getvalue())["auto_update"])

    def test_parse_paths_arg_supports_semicolon_and_comma(self):
        paths = mole.parse_paths_arg(r"C:\A;C:\B, C:\C")
        self.assertEqual(paths, [Path(r"C:\A"), Path(r"C:\B"), Path(r"C:\C")])

    def test_git_root_is_protected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            self.assertTrue(mole.is_protected_path(root))

    def test_build_fs_category_contains_up_entry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "dir1").mkdir()
            (root / "file1.txt").write_bytes(b"x")

            cat = mole.build_fs_category(root)

            self.assertTrue(cat.key.startswith("fs:"))
            self.assertEqual(cat.items[0].error, "up")

    def test_run_optimize_windows_update_dry_run(self):
        action = next(a for a in mole.OPTIMIZE_ACTIONS if a.key == "windows-update")
        ok, res = mole.run_optimize(action, dry_run=True)
        self.assertTrue(ok)
        self.assertIn("dry-run", res)

    def test_dir_size_scandir_counts_nested_and_respects_budget(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.txt").write_bytes(b"x" * 100)
            sub = root / "sub"
            sub.mkdir()
            (sub / "b.txt").write_bytes(b"y" * 250)
            self.assertEqual(mole.dir_size(root), 350)

            seen = []
            total = mole.dir_size(root, on_progress=lambda n: seen.append(n))
            self.assertEqual(total, 350)
            self.assertTrue(seen)

            capped = mole.dir_size(root, max_files=1)
            self.assertLessEqual(capped, 350)
            self.assertGreater(capped, 0)

    @staticmethod
    def _make_junction(link: Path, target: Path) -> bool:
        """Create a real Windows directory junction. False when unavailable."""
        if os.name != "nt":
            return False
        import subprocess

        r = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True
        )
        return r.returncode == 0 and link.exists()

    def test_dir_size_does_not_follow_directory_junctions(self):
        # pnpm's node_modules is a farm of junctions pointing back into a shared
        # store. DirEntry.is_symlink() is False for a junction, so a walker that
        # only checks that descends through them and cycles: on a real pnpm repo
        # this reached depth 191 and never terminated.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "store"
            (root / "pkg").mkdir(parents=True)
            (root / "pkg" / "f.bin").write_bytes(b"z" * 500)
            farm = Path(td) / "node_modules"
            farm.mkdir()
            if not self._make_junction(farm / "pkg", root / "pkg"):
                self.skipTest("directory junctions unavailable")

            # The junction target is counted where it lives, never through the link.
            self.assertEqual(mole.dir_size(root), 500)
            self.assertEqual(mole.dir_size(farm), 0)

    def test_dir_size_terminates_on_cyclic_junction(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "a"
            (root / "deep").mkdir(parents=True)
            (root / "deep" / "f.bin").write_bytes(b"q" * 42)
            if not self._make_junction(root / "deep" / "loop", root):
                self.skipTest("directory junctions unavailable")

            # Without junction pruning this recurses until RecursionError.
            self.assertEqual(mole.dir_size(root), 42)

    def test_iter_dev_folders_does_not_descend_through_junctions(self):
        with tempfile.TemporaryDirectory() as td:
            real = Path(td) / "real"
            (real / "sub" / "node_modules").mkdir(parents=True)
            linked = Path(td) / "linked"
            if not self._make_junction(linked, real):
                self.skipTest("directory junctions unavailable")

            found = [p for _t, p in mole.iter_dev_folders([Path(td)])]

            self.assertIn(real / "sub" / "node_modules", found)
            self.assertNotIn(linked / "sub" / "node_modules", found)

    def test_sized_dir_reports_truncation_and_skips_caching_it(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "big"
            root.mkdir()
            (root / "f.bin").write_bytes(b"w" * 64)

            size, truncated = mole.sized_dir(root)
            self.assertEqual(size, 64)
            self.assertFalse(truncated)

            cache: dict = {}
            with mock.patch.object(
                mole, "dir_size", side_effect=lambda p, **kw: (kw["on_truncated"](), 10)[1]
            ):
                size, truncated = mole.sized_dir(root, cache, max_seconds=0.01)
            self.assertTrue(truncated)
            # A lower bound must never be cached as if it were the real size.
            self.assertEqual(cache, {})

    def test_git_dirs_are_pruned_from_scans(self):
        self.assertIn(".git", mole.SKIP_DIRS)

    def test_scan_filter_matches_is_protected_path_on_denylist(self):
        with tempfile.TemporaryDirectory() as td:
            deny = Path(td) / "data"
            deny.mkdir()
            (Path(td) / "database").mkdir()
            with mock.patch.object(mole, "load_denylist", return_value=[deny]):
                sf = mole.ScanFilter(whitelist=[])
                self.assertTrue(sf.rejects(deny))
                self.assertTrue(sf.rejects(deny / "sub"))
                self.assertFalse(sf.rejects(Path(td) / "database"))

    def test_scan_filter_rejects_repo_roots_and_whitelist(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            (repo / ".git").mkdir(parents=True)
            keep = Path(td) / "keep"
            keep.mkdir()
            sf = mole.ScanFilter(whitelist=[keep])
            self.assertTrue(sf.rejects(repo))
            self.assertTrue(sf.rejects(keep))
            self.assertTrue(sf.rejects(keep / "nested"))
            self.assertFalse(sf.rejects(Path(td) / "plain"))

    def test_purge_scan_streams_items_and_honours_cancel(self):
        import threading

        with tempfile.TemporaryDirectory() as td:
            for name in ("one", "two", "three"):
                nm = Path(td) / name / "node_modules"
                nm.mkdir(parents=True)
                (nm / "x.js").write_bytes(b"j" * 128)

            events = []
            cancel = threading.Event()
            mole._serve_scan(
                {"id": "s1", "mode": "purge", "paths": [td], "no_cache": True},
                events.append,
                cancel,
            )

            kinds = [e["ev"] for e in events]
            self.assertIn("item", kinds)
            self.assertIn("progress", kinds)
            paths = {e["path"] for e in events if e["ev"] == "item"}
            self.assertEqual(len(paths), 3)
            # No item may be emitted twice (streamed + flushed at the end).
            self.assertEqual(len([e for e in events if e["ev"] == "item"]), 3)
            self.assertTrue(events[-1]["ok"])

            events.clear()
            cancel.set()
            mole._serve_scan(
                {"id": "s2", "mode": "purge", "paths": [td], "no_cache": True},
                events.append,
                cancel,
            )
            self.assertTrue(events[-1].get("cancelled"))

    def test_size_cache_roundtrip_and_invalidation(self):
        with tempfile.TemporaryDirectory() as td:
            cache_file = Path(td) / "cache.json"
            with mock.patch.object(mole, "CACHE_FILE", cache_file):
                target = Path(td) / "data"
                target.mkdir()
                cache = mole.load_size_cache()
                self.assertEqual(cache, {})
                mtime = target.stat().st_mtime
                mole.cache_set(cache, target, mtime, 1234)
                mole.save_size_cache(cache)

                reloaded = mole.load_size_cache()
                self.assertEqual(mole.cache_get(reloaded, target, mtime), 1234)
                self.assertIsNone(mole.cache_get(reloaded, target, mtime + 10))

    def test_should_redraw_throttles_idle_and_allows_active(self):
        self.assertTrue(
            mole.should_redraw(last_draw=0.0, now=1.0, scanner_active=True, min_interval=0.08)
        )
        self.assertFalse(
            mole.should_redraw(last_draw=1.0, now=1.02, scanner_active=True, min_interval=0.08)
        )
        self.assertFalse(
            mole.should_redraw(last_draw=0.0, now=100.0, scanner_active=False, min_interval=0.08)
        )

    def test_scanner_parallel_sizes_clean_categories(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            proj = root / "proj"
            (proj / "node_modules").mkdir(parents=True)
            (proj / "node_modules" / "big.js").write_bytes(b"z" * 5000)
            sc = mole.Scanner(profile="purge", roots=[root])
            sc.run()
            self.assertTrue(sc.done)
            total = sum(c.total for c in sc.categories)
            self.assertGreaterEqual(total, 5000)

    def test_scanner_uses_size_cache_on_second_run(self):
        with tempfile.TemporaryDirectory() as td:
            cache_file = Path(td) / "cache.json"
            with mock.patch.object(mole, "CACHE_FILE", cache_file):
                root = Path(td) / "proj"
                (root / "node_modules").mkdir(parents=True)
                (root / "node_modules" / "x.js").write_bytes(b"q" * 4000)

                sc1 = mole.Scanner(profile="purge", roots=[Path(td)])
                sc1.run()
                self.assertTrue(cache_file.exists())

                with mock.patch.object(
                    mole, "dir_size", side_effect=AssertionError("should be cached")
                ):
                    sc2 = mole.Scanner(profile="purge", roots=[Path(td)])
                    sc2.run()
                total = sum(c.total for c in sc2.categories)
                self.assertGreaterEqual(total, 4000)

    def test_scanner_use_cache_false_skips_load(self):
        with tempfile.TemporaryDirectory() as td:
            cache_file = Path(td) / "cache.json"
            cache_file.write_text('{"x": {"mtime": 1, "size": 9}}', encoding="utf-8")
            with mock.patch.object(mole, "CACHE_FILE", cache_file):
                sc = mole.Scanner(profile="idle", use_cache=False)
                self.assertEqual(sc.cache, {})

    def test_denylist_uses_prefix_not_substring(self):
        with tempfile.TemporaryDirectory() as td:
            deny = Path(td) / "data"
            deny.mkdir()
            with mock.patch.object(mole, "load_denylist", return_value=[deny]):
                # exact and real child are protected
                self.assertTrue(mole.is_protected_path(deny))
                self.assertTrue(mole.is_protected_path(deny / "sub"))
                # sibling that merely shares a name prefix is NOT protected
                self.assertFalse(mole.is_protected_path(Path(td) / "database"))

    def test_delete_path_no_send2trash_does_not_permanently_delete(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "keep.txt"
            f.write_bytes(b"data")
            with (
                mock.patch.object(mole, "send2trash", None),
                mock.patch.object(mole, "load_config", return_value={"quarantine_enabled": False}),
            ):
                err = mole.delete_path(f, use_trash=True, dry_run=False)
            self.assertIsNotNone(err)
            self.assertTrue(f.exists())  # must NOT be permanently deleted

    def test_quarantine_roundtrip_restores_original_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "project-cache"
            source.mkdir()
            (source / "data.txt").write_text("safe", encoding="utf-8")
            vault = root / "vault"
            with (
                mock.patch.object(mole, "QUARANTINE_DIR", vault),
                mock.patch.object(mole, "QUARANTINE_INDEX", vault / "index.json"),
                mock.patch.object(mole, "git_delete_risk", return_value=""),
                mock.patch.object(mole, "log_operation"),
            ):
                self.assertIsNone(mole.quarantine_path(source, size=4))
                self.assertFalse(source.exists())
                entry = mole._quarantine_entries()[0]
                self.assertIsNone(mole.restore_quarantine(entry["id"]))
            self.assertEqual((source / "data.txt").read_text(encoding="utf-8"), "safe")

    def test_git_delete_risk_blocks_dirty_target(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            target = root / "src"
            target.mkdir()
            completed = mock.Mock(returncode=0, stdout=" M src/app.py\n")
            with mock.patch.object(mole.subprocess, "run", return_value=completed):
                self.assertIn("modified", mole.git_delete_risk(target))

    def test_secret_scan_redacts_detected_value(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            value = "ghp_1234567890abcdefghijklmnop"
            (root / ".env").write_text(f"TOKEN={value}\n", encoding="utf-8")
            with mock.patch.object(mole, "log_security_event"):
                result = mole.scan_secrets(root)
            self.assertEqual(len(result["findings"]), 1)
            self.assertNotIn(value, result["findings"][0]["preview"])

    def test_security_log_detects_tampering(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            log = root / "security.jsonl"
            key = root / "security.key"
            with (
                mock.patch.object(mole, "SECURITY_LOG_FILE", log),
                mock.patch.object(mole, "SECURITY_KEY_FILE", key),
                mock.patch.object(mole, "WMOLE_DIR", root),
            ):
                mole.log_security_event("test", {"ok": True})
                rows, valid = mole.read_security_log()
                self.assertTrue(valid)
                self.assertEqual(rows[0]["event"], "test")
                log.write_text(
                    log.read_text(encoding="utf-8").replace("test", "evil"), encoding="utf-8"
                )
                _, valid = mole.read_security_log()
                self.assertFalse(valid)

    def test_supply_chain_audit_builds_sbom_and_reports_tool_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
            (root / "package-lock.json").write_text('{"lockfileVersion":3}', encoding="utf-8")
            with (
                mock.patch.object(
                    mole,
                    "_run_audit",
                    return_value={
                        "tool": "npm",
                        "status": "ok",
                        "code": 0,
                        "output": "{}",
                    },
                ),
                mock.patch.object(mole, "log_security_event"),
            ):
                result = mole.supply_chain_audit(root)
            self.assertEqual(len(result["sbom"]), 2)
            self.assertEqual(result["audits"][0]["status"], "ok")

    def test_process_protection_blocks_configured_developer_process(self):
        fake_proc = mock.Mock()
        fake_proc.name.return_value = "Code.exe"
        with (
            mock.patch.object(mole.psutil, "Process", return_value=fake_proc),
            mock.patch.object(
                mole,
                "load_config",
                return_value={
                    "protected_processes": ["code.exe"],
                },
            ),
        ):
            self.assertIn("protected developer process", mole.process_protection_reason(42))

    def test_is_leftover_match_is_strict(self):
        tokens = mole.normalize_app_tokens("GitHub Desktop")
        self.assertTrue(mole.is_leftover_match(Path("GitHubDesktop"), tokens))
        self.assertTrue(mole.is_leftover_match(Path("git"), ["git"]))  # exact short token ok
        # unrelated folder must not match short tokens
        self.assertFalse(mole.is_leftover_match(Path("gitignore"), ["vlc", "obs"]))
        # "git" token must not loosely match a longer unrelated folder
        self.assertFalse(mole.is_leftover_match(Path("gitkraken"), ["git"]))

    def test_cache_get_ttl_expiry(self):
        cache = {}
        p = Path("C:/tmp/x")
        mole.cache_set(cache, p, 123.0, 999)
        # force an old scanned_at
        cache[str(p)]["scanned_at"] = 0
        self.assertIsNone(mole.cache_get(cache, p, 123.0))

    def test_cli_optimize_json_skips_high_risk_without_yes(self):
        buf = io.StringIO()
        # Mock run_optimize so no real system commands execute during the test.
        with mock.patch.object(mole, "run_optimize", return_value=(True, "ran")):
            with contextlib.redirect_stdout(buf):
                mole.cli_optimize(dry_run=False, json_out=True, yes=False)
        data = json.loads(buf.getvalue())
        highs = [r for r in data["results"] if r.get("risk") == "high"]
        self.assertTrue(highs)
        self.assertTrue(all("requires --yes" in r["result"] for r in highs))
        # high-risk actions must never have been executed
        self.assertTrue(all(r["result"] != "ran" for r in highs))


class DoctorReportTests(unittest.TestCase):
    def test_doctor_report_rows_follow_the_check_schema(self):
        with (
            mock.patch.object(
                mole,
                "_tool_version",
                side_effect=lambda name, **kw: mole._doctor_row(name, "unavailable", "stub"),
            ),
            mock.patch.object(mole, "_doctor_caches", return_value=[]),
            mock.patch.object(mole, "_doctor_wmole_state", return_value=[]),
        ):
            report = mole.doctor_report()

        self.assertIn("checks", report)
        self.assertIn("summary", report)
        for row in report["checks"]:
            self.assertEqual(set(row), {"check", "status", "detail"})
            self.assertIn(row["status"], ("ok", "warn", "fail", "unavailable"))
        names = [row["check"] for row in report["checks"]]
        for tool in mole.DOCTOR_TOOLS:
            self.assertIn(tool, names)
        self.assertEqual(sum(report["summary"].values()), len(report["checks"]))

    def test_doctor_path_check_flags_duplicates_and_missing_entries(self):
        with tempfile.TemporaryDirectory() as td:
            real = str(Path(td) / "bin")
            (Path(td) / "bin").mkdir()
            ghost = str(Path(td) / "nope")
            path_value = os.pathsep.join([real, real, ghost])
            with mock.patch.dict(os.environ, {"PATH": path_value}, clear=False):
                rows = {row["check"]: row for row in mole._doctor_path_entries()}
        self.assertEqual(rows["PATH duplicates"]["status"], "warn")
        self.assertEqual(rows["PATH missing"]["status"], "warn")
        self.assertIn("nope", rows["PATH missing"]["detail"])

    def test_tool_version_reports_unavailable_when_not_on_path(self):
        with mock.patch.object(mole.shutil, "which", return_value=None):
            row = mole._tool_version("definitely-not-a-tool")
        self.assertEqual(row["status"], "unavailable")

    def test_cli_doctor_json_is_machine_readable(self):
        buf = io.StringIO()
        stub = {
            "checks": [{"check": "x", "status": "ok", "detail": "d"}],
            "summary": {"ok": 1},
            "healthy": True,
        }
        with mock.patch.object(mole, "doctor_report", return_value=stub):
            with contextlib.redirect_stdout(buf):
                mole.cli_doctor(json_out=True)
        self.assertEqual(json.loads(buf.getvalue()), stub)


class ProjectRcTests(unittest.TestCase):
    def setUp(self):
        mole._PROJECT_RC_CACHE.clear()

    def tearDown(self):
        mole._PROJECT_RC_CACHE.clear()

    def _repo(self, td, payload):
        root = Path(td) / "repo"
        root.mkdir()
        if payload is not None:
            (root / mole.WMOLERC_NAME).write_text(payload, encoding="utf-8")
        return root

    def test_load_project_rc_parses_known_keys(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(
                td,
                json.dumps(
                    {"purge": ["dist", "node_modules"], "keep": ["packages/*/dist"], "max_depth": 4}
                ),
            )
            rc = mole.load_project_rc(root)
        self.assertEqual(rc["purge"], ["dist", "node_modules"])
        self.assertEqual(rc["keep"], ["packages/*/dist"])
        self.assertEqual(rc["max_depth"], 4)

    def test_broken_rc_is_ignored_and_debug_logged(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(td, "{not json")
            with mock.patch.object(mole, "_debug_log") as logged:
                rc = mole.load_project_rc(root)
        self.assertIsNone(rc)
        self.assertTrue(logged.called)

    def test_keep_glob_protects_matching_subtree(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(td, json.dumps({"keep": ["packages/*/dist"]}))
            rc = mole.load_project_rc(root)
            kept = root / "packages" / "ui" / "dist"
            nested = kept / "assets"
            other = root / "apps" / "web" / "dist"
        self.assertTrue(mole.rc_is_kept(rc, kept))
        self.assertTrue(mole.rc_is_kept(rc, nested))
        self.assertFalse(mole.rc_is_kept(rc, other))

    def test_rc_allows_purge_honors_names_and_max_depth(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(td, json.dumps({"purge": ["dist"], "max_depth": 2}))
            rc = mole.load_project_rc(root)
            self.assertTrue(mole.rc_allows_purge(rc, root / "app" / "dist"))
            # name not listed in `purge`
            self.assertFalse(mole.rc_allows_purge(rc, root / "app" / "node_modules"))
            # deeper than max_depth
            self.assertFalse(mole.rc_allows_purge(rc, root / "a" / "b" / "dist"))
            # outside the rc root is untouched by the rc
            self.assertTrue(mole.rc_allows_purge(rc, Path(td) / "other" / "dist"))

    def test_find_project_rc_walks_up_and_missing_rc_allows_everything(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(td, json.dumps({"purge": ["dist"]}))
            deep = root / "a" / "b"
            deep.mkdir(parents=True)
            self.assertIsNotNone(mole.find_project_rc(deep))
            mole._PROJECT_RC_CACHE.clear()
            plain = Path(td) / "plain"
            plain.mkdir()
            self.assertIsNone(mole.find_project_rc(plain))
            self.assertTrue(mole.rc_allows_path(plain / "dist"))


class UndoTests(unittest.TestCase):
    def test_undo_entries_are_newest_first_with_readable_fields(self):
        entries = [
            {"id": "old", "original": r"C:\a", "name": "a", "size": 10, "created": 100},
            {"id": "new", "original": r"C:\b", "name": "b", "size": 20, "created": 200},
        ]
        with mock.patch.object(mole, "_quarantine_entries", return_value=entries):
            rows = mole.undo_entries()
        self.assertEqual([r["id"] for r in rows], ["new", "old"])
        self.assertEqual(rows[0]["path"], r"C:\b")
        self.assertTrue(rows[0]["created_at"])

    def test_cli_undo_json_listing_includes_recycle_bin_hint(self):
        buf = io.StringIO()
        with mock.patch.object(mole, "_quarantine_entries", return_value=[]):
            with contextlib.redirect_stdout(buf):
                mole.cli_undo(json_out=True)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["count"], 0)
        self.assertIn("Recycle Bin", data["hint"])

    def test_cli_undo_with_id_calls_restore_quarantine(self):
        buf = io.StringIO()
        with mock.patch.object(mole, "restore_quarantine", return_value=None) as restore:
            with contextlib.redirect_stdout(buf):
                mole.cli_undo(entry_id="abc123", json_out=True)
        restore.assert_called_once_with("abc123")
        self.assertTrue(json.loads(buf.getvalue())["restored"])

    def test_cli_undo_reports_restore_failure(self):
        buf = io.StringIO()
        with mock.patch.object(
            mole, "restore_quarantine", return_value="original path already exists"
        ):
            with contextlib.redirect_stdout(buf):
                mole.cli_undo(entry_id="abc123", json_out=True)
        data = json.loads(buf.getvalue())
        self.assertFalse(data["restored"])
        self.assertIn("already exists", data["error"])


class GitHookTests(unittest.TestCase):
    def _repo(self, td):
        root = Path(td) / "repo"
        (root / ".git" / "hooks").mkdir(parents=True)
        return root

    def test_frozen_hook_command_omits_script_path(self):
        # PyInstaller build'inde __file__ geçici çıkarma dizinini gösterir ve
        # süreç bitince silinir; hook'a yazılırsa kalıcı olarak bozulur.
        with (
            mock.patch.object(mole.sys, "frozen", True, create=True),
            mock.patch.object(mole.sys, "executable", r"C:\Program Files\wmole\wmole.exe"),
        ):
            command = mole._hook_command()
        self.assertIn("wmole.exe", command)
        self.assertNotIn("mole.py", command)

    def test_source_hook_command_includes_script_path(self):
        with mock.patch.object(mole.sys, "frozen", False, create=True):
            command = mole._hook_command()
        self.assertIn("mole.py", command)

    def test_installed_hook_body_uses_hook_command(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(td)
            with (
                mock.patch.object(mole, "log_security_event"),
                mock.patch.object(mole, "_hook_command", return_value='"X.exe"'),
            ):
                mole.install_pre_commit_hook(root)
            body = mole.hook_path(root).read_text(encoding="utf-8")
        self.assertIn('"X.exe" hook --run', body)

    def test_install_and_uninstall_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(td)
            with mock.patch.object(mole, "log_security_event"):
                res = mole.install_pre_commit_hook(root)
                self.assertTrue(res["ok"])
                hook = mole.hook_path(root)
                self.assertTrue(hook.exists())
                self.assertIn(mole.HOOK_SIGNATURE, hook.read_text(encoding="utf-8"))

                res = mole.uninstall_pre_commit_hook(root)
            self.assertTrue(res["ok"])
            self.assertFalse(mole.hook_path(root).exists())

    def test_install_refuses_to_clobber_a_foreign_hook_without_force(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(td)
            hook = mole.hook_path(root)
            hook.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
            res = mole.install_pre_commit_hook(root)
            self.assertFalse(res["ok"])
            self.assertIn("--force", res["error"])
            self.assertIn("echo mine", hook.read_text(encoding="utf-8"))

            with mock.patch.object(mole, "log_security_event"):
                forced = mole.install_pre_commit_hook(root, force=True)
            self.assertTrue(forced["ok"])
            self.assertIn(mole.HOOK_SIGNATURE, hook.read_text(encoding="utf-8"))

    def test_uninstall_leaves_foreign_hooks_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(td)
            hook = mole.hook_path(root)
            hook.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
            res = mole.uninstall_pre_commit_hook(root)
            self.assertFalse(res["ok"])
            self.assertTrue(hook.exists())

    def test_git_repo_root_finds_the_enclosing_repo(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(td)
            nested = root / "src" / "pkg"
            nested.mkdir(parents=True)
            self.assertEqual(mole.git_repo_root(nested), root)
            self.assertIsNone(mole.git_repo_root(Path(td)))

    def test_scan_staged_secrets_flags_a_staged_key(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(td)
            leaky = root / "config.env"
            leaky.write_text("AWS_KEY=AKIAABCDEFGHIJKLMNOP\n", encoding="utf-8")
            with mock.patch.object(mole, "_staged_files", return_value=[leaky]):
                report = mole.scan_staged_secrets(root)
        self.assertEqual(report["scanned"], 1)
        self.assertTrue(report["findings"])
        self.assertNotIn("AKIAABCDEFGHIJKLMNOP", json.dumps(report))

    def test_cli_hook_run_exits_nonzero_on_findings(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(td)
            leaky = root / "config.env"
            leaky.write_text("AWS_KEY=AKIAABCDEFGHIJKLMNOP\n", encoding="utf-8")
            buf = io.StringIO()
            with mock.patch.object(mole, "_staged_files", return_value=[leaky]):
                with contextlib.redirect_stdout(buf):
                    code = mole.cli_hook("run", json_out=True, cwd=root)
            self.assertEqual(code, 1)

            buf = io.StringIO()
            with mock.patch.object(mole, "_staged_files", return_value=[]):
                with contextlib.redirect_stdout(buf):
                    code = mole.cli_hook("run", json_out=True, cwd=root)
            self.assertEqual(code, 0)

    def test_cli_hook_outside_a_repo_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = mole.cli_hook("install", json_out=True, cwd=Path(td))
        self.assertEqual(code, 1)
        self.assertIn("git repository", json.loads(buf.getvalue())["error"])


class PortsProjectTests(unittest.TestCase):
    def test_process_project_name_prefers_the_git_repo_name(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "my-repo"
            (root / ".git").mkdir(parents=True)
            nested = root / "apps" / "api"
            nested.mkdir(parents=True)
            fake_psutil = mock.Mock(Error=Exception)
            fake_psutil.Process.return_value.cwd.return_value = str(nested)
            with mock.patch.object(mole, "psutil", fake_psutil):
                self.assertEqual(mole.process_project_name(4242), "my-repo")

    def test_process_project_name_is_blank_on_access_denied(self):
        class Denied(Exception):
            pass

        fake_psutil = mock.Mock(Error=Denied)
        fake_psutil.Process.side_effect = Denied("nope")
        with mock.patch.object(mole, "psutil", fake_psutil):
            self.assertEqual(mole.process_project_name(1), "")
        self.assertEqual(mole.process_project_name(0), "")

    def test_cli_ports_json_carries_the_project_field(self):
        rows = [
            {
                "proto": "TCP",
                "ip": "127.0.0.1",
                "port": 3000,
                "pid": 10,
                "process": "node.exe",
                "exe": "",
                "project": "my-repo",
                "hint": "",
            }
        ]
        buf = io.StringIO()
        with mock.patch.object(mole, "list_dev_ports", return_value=rows):
            with contextlib.redirect_stdout(buf):
                mole.cli_ports(json_out=True)
        self.assertEqual(json.loads(buf.getvalue())["ports"][0]["project"], "my-repo")

    def test_cli_ports_text_output_shows_the_project_column(self):
        rows = [
            {
                "proto": "TCP",
                "ip": "127.0.0.1",
                "port": 3000,
                "pid": 10,
                "process": "node.exe",
                "exe": "",
                "project": "my-repo",
                "hint": "Next.js",
            }
        ]
        buf = io.StringIO()
        with mock.patch.object(mole, "list_dev_ports", return_value=rows):
            with contextlib.redirect_stdout(buf):
                mole.cli_ports(json_out=False)
        out = buf.getvalue()
        self.assertIn("PROJECT", out)
        self.assertIn("my-repo", out)


class DuplicateHashTests(unittest.TestCase):
    def test_quick_digest_only_reads_the_file_edges(self):
        with tempfile.TemporaryDirectory() as td:
            head = b"H" * 65536
            tail = b"T" * 65536
            a = Path(td) / "a.bin"
            b = Path(td) / "b.bin"
            a.write_bytes(head + b"\x00" * 1000 + tail)
            b.write_bytes(head + b"\xff" * 1000 + tail)
            # Same edges -> same quick digest, different full digest.
            self.assertEqual(mole._file_digest(a, quick=True), mole._file_digest(b, quick=True))
            self.assertNotEqual(mole._file_digest(a), mole._file_digest(b))
            self.assertEqual(len(mole._file_digest(a)), 32)

    def test_duplicate_groups_skips_full_hash_for_unique_prehashes(self):
        with tempfile.TemporaryDirectory() as td:
            same_a = Path(td) / "same_a.bin"
            same_b = Path(td) / "same_b.bin"
            unique = Path(td) / "unique.bin"
            same_a.write_bytes(b"payload" * 100)
            same_b.write_bytes(b"payload" * 100)
            unique.write_bytes(b"different" * 100)

            real_digest = mole._file_digest
            full_calls = []

            def spy(path, quick=False, edge=65536):
                if not quick:
                    full_calls.append(path)
                return real_digest(path, quick=quick, edge=edge)

            with mock.patch.object(mole, "_file_digest", side_effect=spy):
                groups = mole._duplicate_groups([same_a, same_b, unique])

        self.assertEqual(len(groups), 1)
        self.assertEqual(sorted(next(iter(groups.values()))), sorted([same_a, same_b]))
        # The unique file never reached the expensive full-hash pass.
        self.assertNotIn(unique, full_calls)
        self.assertEqual(sorted(full_calls), sorted([same_a, same_b]))

    def test_duplicate_groups_is_empty_when_nothing_matches(self):
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a.bin"
            b = Path(td) / "b.bin"
            a.write_bytes(b"a" * 500)
            b.write_bytes(b"b" * 500)
            self.assertEqual(mole._duplicate_groups([a, b]), {})

    # ---- regressions: updater asset handling ----
    def test_setup_exe_is_recognised_as_installer(self):
        # `setup$` never matched "...-setup.exe": the installer was copied over wmole.exe.
        self.assertTrue(mole._is_installer_asset("wmole-0.7.0-setup.exe"))
        self.assertTrue(mole._is_installer_asset("wmole.msi"))
        self.assertFalse(mole._is_installer_asset("wmole.exe"))
        self.assertFalse(mole._is_installer_asset("wmole-0.7.0-setup.exe.sha256"))

    def test_update_asset_prefers_own_exe_and_never_picks_checksum(self):
        assets = [
            {"name": "wmole-0.7.0-setup.exe.sha256"},
            {"name": "wmole-0.7.0-setup.exe"},
            {"name": "wmole.exe"},
        ]
        with mock.patch.object(mole.sys, "executable", r"C:\tools\wmole.exe"):
            self.assertEqual(mole._pick_update_asset(assets)["name"], "wmole.exe")
        with mock.patch.object(mole.sys, "executable", r"C:\tools\other.exe"):
            self.assertEqual(mole._pick_update_asset(assets)["name"], "wmole-0.7.0-setup.exe")
        self.assertIsNone(mole._pick_installer_asset([{"name": "notes.sha256"}]))

    def test_sidecar_never_applies_pending_update(self):
        with (
            mock.patch.object(mole.sys, "frozen", True, create=True),
            mock.patch.object(mole.sys, "argv", ["wmole.exe", "serve"]),
            mock.patch.object(mole, "_launch_updated") as launch,
        ):
            self.assertFalse(mole.apply_pending_update())
        launch.assert_not_called()

    # ---- regressions: quarantine must never lose data ----
    def _vault(self, root):
        vault = root / "vault"
        return (
            mock.patch.object(mole, "QUARANTINE_DIR", vault),
            mock.patch.object(mole, "QUARANTINE_INDEX", vault / "index.json"),
            mock.patch.object(mole, "git_delete_risk", return_value=""),
            mock.patch.object(mole, "log_operation"),
            mock.patch.object(mole, "log_security_event"),
        )

    def test_quarantine_of_folder_with_locked_file_leaves_source_intact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "cache"
            source.mkdir()
            for i in range(3):
                (source / f"f{i}.txt").write_text("data", encoding="utf-8")
            with contextlib.ExitStack() as stack:
                for patch in self._vault(root):
                    stack.enter_context(patch)
                with open(source / "locked.txt", "w") as handle:
                    handle.write("busy")
                    handle.flush()
                    error = mole.quarantine_path(source, size=1)
                self.assertIsNotNone(error)
                self.assertEqual(mole._quarantine_entries(), [])
            self.assertEqual(
                sorted(p.name for p in source.iterdir()),
                ["f0.txt", "f1.txt", "f2.txt", "locked.txt"],
            )

    def test_expired_entry_with_blank_id_does_not_wipe_quarantine(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with contextlib.ExitStack() as stack:
                for patch in self._vault(root):
                    stack.enter_context(patch)
                keep = root / "vault" / "999-abcd1234" / "keep.txt"
                keep.parent.mkdir(parents=True)
                keep.write_text("x", encoding="utf-8")
                mole._save_quarantine_entries(
                    [
                        {"id": "", "created": 1},
                        {"id": "..", "created": 1},
                        {"id": "999-abcd1234", "created": 9_999_999_999},
                    ]
                )
                self.assertEqual(mole.purge_expired_quarantine(), 2)
                self.assertTrue(keep.exists())
                self.assertEqual(len(mole._quarantine_entries()), 1)

    # ---- regressions: destructive suggestions ----
    def test_critical_and_own_processes_are_never_killable(self):
        fake_proc = mock.Mock()
        fake_proc.name.return_value = "csrss.exe"
        with (
            mock.patch.object(mole.psutil, "Process", return_value=fake_proc),
            mock.patch.object(mole, "load_config", return_value={}),
        ):
            self.assertIn("critical", mole.process_protection_reason(4242))
        self.assertIn("critical", mole.process_protection_reason(os.getpid()))
        self.assertEqual(mole.kill_pid(os.getpid())[0], False)

    def test_leftovers_skip_vendor_folder_shared_with_other_apps(self):
        with tempfile.TemporaryDirectory() as td:
            appdata = Path(td)
            (appdata / "Microsoft").mkdir()
            (appdata / "Code").mkdir()
            app = {"name": "Code", "publisher": "Microsoft Corporation"}
            others = [app, {"name": "Edge", "publisher": "Microsoft Corporation"}]
            with mock.patch.object(mole, "list_installed_apps", return_value=others):
                shared = {i.path.name for i in mole.find_leftover_candidates(app, roots=[appdata])}
            with mock.patch.object(mole, "list_installed_apps", return_value=[app]):
                alone = {i.path.name for i in mole.find_leftover_candidates(app, roots=[appdata])}
        self.assertEqual(shared, {"Code"})
        self.assertEqual(alone, {"Code", "Microsoft"})

    def test_system_cache_dirs_are_cleanable_but_rest_of_windows_is_not(self):
        self.assertFalse(mole.is_protected_path(Path(r"C:\Windows\Temp")))
        self.assertFalse(mole.is_protected_path(Path(r"C:\Windows\Temp\junk.tmp")))
        self.assertFalse(
            mole.is_protected_path(Path(r"C:\Windows\SoftwareDistribution\Download\abc"))
        )
        self.assertTrue(mole.is_protected_path(Path(r"C:\Windows\Temporary")))
        self.assertTrue(mole.is_protected_path(Path(r"C:\Windows\SoftwareDistribution")))
        self.assertTrue(mole.is_protected_path(Path(r"C:\Windows\System32\drivers")))

    def test_temp_root_is_emptied_not_removed(self):
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td) / "Temp"
            temp.mkdir()
            old_file = temp / "old.tmp"
            old_dir = temp / "olddir"
            fresh = temp / "fresh.tmp"
            busy = temp / "busy.tmp"
            old_dir.mkdir()
            for f in (old_file, old_dir / "x.bin", fresh, busy):
                f.write_text("data", encoding="utf-8")
            stale = mole.time.time() - 3 * 86400
            for f in (old_file, old_dir / "x.bin", old_dir, busy):
                os.utime(f, (stale, stale))
            with (
                mock.patch.object(mole, "TEMP", temp),
                mock.patch.object(mole, "log_operation"),
                open(busy, "r+") as handle,
            ):
                self.assertTrue(mole._is_contents_only_dir(temp))
                self.assertIsNone(mole.delete_path(temp, use_trash=True, dry_run=True))
                self.assertTrue(old_file.exists())  # dry run touches nothing
                self.assertIn(
                    "could not be removed", mole.delete_path(temp, use_trash=True, dry_run=False)
                )
                handle.read()
            self.assertEqual(sorted(p.name for p in temp.iterdir()), ["busy.tmp", "fresh.tmp"])

    def test_other_drive_goes_to_recycle_bin_not_quarantine(self):
        with (
            mock.patch.object(mole, "QUARANTINE_DIR", Path(r"C:\Users\x\.wmole\quarantine")),
            mock.patch.object(mole, "load_config", return_value={"quarantine_enabled": True}),
        ):
            self.assertTrue(mole._use_quarantine(Path(r"C:\proj\node_modules")))
            self.assertFalse(mole._use_quarantine(Path(r"D:\proj\node_modules")))
        with mock.patch.object(mole, "load_config", return_value={"quarantine_enabled": False}):
            self.assertFalse(mole._use_quarantine(Path(r"C:\proj\node_modules")))

    def test_empty_quarantine_removes_items_and_index(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "cache"
            source.mkdir()
            (source / "f.txt").write_text("data", encoding="utf-8")
            with contextlib.ExitStack() as stack:
                for patch in self._vault(root):
                    stack.enter_context(patch)
                self.assertIsNone(mole.quarantine_path(source, size=4))
                self.assertEqual(mole.empty_quarantine(), {"removed": 1, "bytes": 4, "failed": 0})
                self.assertEqual(mole._quarantine_entries(), [])
                self.assertEqual([p.name for p in (root / "vault").iterdir()], ["index.json"])

    def test_download_rejects_wrong_checksum_and_deletes_file(self):
        body = b"installer-bytes"
        good = mole.hashlib.sha256(body).hexdigest()

        def fake_urlopen(*_a, **_k):
            resp = mock.MagicMock()
            resp.__enter__.return_value = resp
            resp.headers = {"Content-Length": str(len(body))}
            resp.read.side_effect = [body, b""]
            return resp

        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "wmole.exe"
            with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                mole._download("https://example.invalid/x", dest, sha256=good)
                self.assertEqual(mole._sha256_file(dest), good)
                with self.assertRaises(ValueError):
                    mole._download("https://example.invalid/x", dest, sha256="0" * 64)
            self.assertFalse(dest.exists())

    def test_asset_sha256_parses_only_valid_github_digest(self):
        self.assertEqual(mole._asset_sha256({"digest": "sha256:" + "AB" * 32}), "ab" * 32)
        self.assertEqual(mole._asset_sha256({"digest": "md5:abcd"}), "")
        self.assertEqual(mole._asset_sha256({}), "")

    def test_tampered_staged_update_is_not_launched(self):
        with tempfile.TemporaryDirectory() as td:
            staged = Path(td) / "wmole.exe"
            staged.write_bytes(b"evil")
            pending = Path(td) / "pending.json"
            pending.write_text(
                json.dumps(
                    {
                        "version": "v99.0.0",
                        "name": "wmole.exe",
                        "path": str(staged),
                        "sha256": "0" * 64,
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(mole.sys, "frozen", True, create=True),
                mock.patch.object(mole.sys, "argv", ["wmole.exe", "status"]),
                mock.patch.object(mole, "PENDING_UPDATE_FILE", pending),
                mock.patch.object(mole, "_auto_update_disabled", return_value=False),
                mock.patch.object(mole, "_launch_updated") as launch,
            ):
                self.assertFalse(mole.apply_pending_update())
            launch.assert_not_called()
            self.assertFalse(pending.exists())

    def test_startup_toggle_writes_startup_approved_flag(self):
        import winreg

        name = "wmole-test-entry"
        sub = mole._APPROVED_KEY + r"\Run"
        try:
            with mock.patch.object(mole, "log_operation"):
                mole.set_startup_enabled("HKCU\\Run", name, False)
                self.assertFalse(mole._startup_enabled("HKCU\\Run", name))
                mole.set_startup_enabled("HKCU\\Run", name, True)
                self.assertTrue(mole._startup_enabled("HKCU\\Run", name))
                with self.assertRaises(OSError):
                    mole.set_startup_enabled("Nowhere", name, False)
        finally:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)

    def test_jetbrains_category_offers_only_cache_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "Toolbox" / "apps").mkdir(parents=True)
            (base / "PyCharm2025.1" / "caches").mkdir(parents=True)
            (base / "PyCharm2025.1" / "plugins").mkdir()
            items = mole.fixed_category_items("jetbrains", base, selected=True)
        self.assertEqual([i.path.name for i in items], ["caches"])


if __name__ == "__main__":
    unittest.main()
