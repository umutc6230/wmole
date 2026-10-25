# Supported environments

Last verified: 2026-09-09.

| Area | Supported scope | Notes |
|---|---|---|
| Windows | Windows 10 22H2 and Windows 11 | Current security updates and WebView2 required. |
| Architecture | x86-64 | The bundled Python sidecar target is `x86_64-pc-windows-msvc`. |
| Python source run | CPython 3.10-3.12 | CI verifies 3.12. The packaged app supplies its sidecar. |
| File system | Local NTFS | Same-volume rename is used for quarantine. Cross-volume copies are hashed before the source is removed. |
| Other storage | exFAT, removable and network paths: best effort | Atomic rename, locking, ACLs and disconnect behavior vary; retain backups for important data. |
| User level | Standard user | Some Optimize actions require elevation and are labelled before execution. |

The automated suite covers protected paths, Git changes, quarantine rollback,
concurrent index writes, recovery reconciliation, malformed protocol input and
cancellation. Installer behavior still needs a clean Windows VM test for every
release. Visual scaling must be checked at 100%, 150% and 200% on the release
candidate.

Product owner: [Umut Çelik](https://github.com/palamut62) · [X](https://x.com/palamut62)
