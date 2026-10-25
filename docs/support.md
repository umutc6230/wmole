# Support guide

## Before sharing diagnostics

Open `%USERPROFILE%\.wmole` in Explorer and inspect the files yourself. Operation
and debug logs can contain local file paths, Windows account names, application
names and project names. Remove anything you do not want to disclose. Never add
credentials, `.env` contents or quarantined files to a support report.

Useful, bounded files are:

- `logs\debug.log`: startup and handled state-read failures.
- The latest relevant lines from `logs\operations.log`.
- `quarantine\index.json` and an affected item's `entry.json`, after redacting
  the `original` and `stored` path fields.
- The application version, Windows version, architecture and whether the action
  ran as a standard user or administrator.

## Corrupt state file

Close wmole, copy `%USERPROFILE%\.wmole` to a safe backup, then validate the named
JSON file. Do not delete the `quarantine` folder. For a quarantine index problem,
keep `index.json`, `index.json.bak` and every item directory together; the next
Security Center load reconciles valid item manifests without deleting user data.

## Missing sidecar

If the status bar remains disconnected, reinstall the matching setup package.
The packaged sidecar must exist beside the Tauri resources and must match the GUI
release. Source builds can recreate it with `scripts\build-windows-release.ps1`.

## Failed update

Keep the current application installed. A failed download or validation must not
be launched. Retry on a stable connection, or download the setup bearing the
same version and architecture from the project's GitHub Releases page. Report
the displayed error and the asset filename.

## File recovery

Use Security Center to restore a quarantined item. wmole will not overwrite an
existing destination. If the original path is occupied, rename that existing
file or folder after inspecting it, then retry restore.

Report reproducible issues at <https://github.com/palamut62/wmole/issues>.

Product owner: [Umut Çelik](https://github.com/palamut62) · [X](https://x.com/palamut62)
