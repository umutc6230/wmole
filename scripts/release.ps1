param(
  [Parameter(Mandatory=$true)][string]$Version,
  [string]$Notes = "",
  [string]$NotesFile = "",
  [switch]$Prerelease,
  [switch]$SkipPush,
  [switch]$SkipBuild
)

# wmole one-shot release pipeline:
#   1. bump installer version
#   2. test + build + verify artifacts
#   3. explicit source commit + push
#   4. tag + GitHub release assets
# Changelog + web download button update themselves at runtime
# via the GitHub Releases API (see index.html: loadReleases).

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$tag = "v$Version"
Write-Host "==> Releasing wmole $tag" -ForegroundColor Cyan

function Invoke-Checked([string]$Label, [scriptblock]$Command) {
  Write-Host "==> $Label" -ForegroundColor Cyan
  & $Command
  if ($LASTEXITCODE -ne 0) { throw "$Label failed ($LASTEXITCODE)" }
}

# --- 1. Sürümü tüm bileşenlerde senkronla (AGENTS.md kuralı) ---
# Sürüm tek yerden girilir; installer + GUI + sidecar birlikte güncellenir.
function Update-VersionLine([string]$RelPath, [string]$Pattern, [string]$Replacement) {
  $full = Join-Path $repoRoot $RelPath
  if (-not (Test-Path $full)) { Write-Warning "version sync: missing $RelPath"; return }
  $content = [IO.File]::ReadAllText($full)
  $updated = [regex]::Replace($content, $Pattern, $Replacement)
  [IO.File]::WriteAllText($full, $updated)   # UTF-8, BOM yok
  Write-Host "   bumped $RelPath -> $Version"
}
Update-VersionLine "installer/wmole.iss"              '#define MyAppVersion "[^"]+"' "#define MyAppVersion `"$Version`""
Push-Location (Join-Path $repoRoot "gui")
try {
  & npm version $Version --no-git-tag-version --allow-same-version
  if ($LASTEXITCODE -ne 0) { throw "npm version sync failed ($LASTEXITCODE)" }
} finally {
  Pop-Location
}
Update-VersionLine "gui/src-tauri/tauri.conf.json"    '(?m)^(\s*)"version": "[^"]+"' "`$1`"version`": `"$Version`""
Update-VersionLine "gui/src-tauri/Cargo.toml"         '(?m)^version = "[^"]+"'       "version = `"$Version`""
Update-VersionLine "mole.py"                          '(?m)^__version__ = "[^"]+"'   "__version__ = `"$Version`""

$versionSources = @{
  "gui/package.json" = (Get-Content "gui/package.json" -Raw | ConvertFrom-Json -AsHashtable)["version"]
  "gui/package-lock.json" = (Get-Content "gui/package-lock.json" -Raw | ConvertFrom-Json -AsHashtable)["version"]
  "gui/src-tauri/tauri.conf.json" = (Get-Content "gui/src-tauri/tauri.conf.json" -Raw | ConvertFrom-Json -AsHashtable)["version"]
}
foreach ($entry in $versionSources.GetEnumerator()) {
  if ($entry.Value -ne $Version) { throw "Version mismatch in $($entry.Key): $($entry.Value)" }
}

# --- 2. Test and build before any remote mutation ---
Invoke-Checked "Python tests" { python -m unittest discover -s tests -q }
Push-Location (Join-Path $repoRoot "gui")
try {
  Invoke-Checked "Frontend install" { npm ci --ignore-scripts --no-audit --no-fund }
  Invoke-Checked "Frontend check" { npm run check }
  Invoke-Checked "Frontend build" { npm run build }
} finally {
  Pop-Location
}
Push-Location (Join-Path $repoRoot "gui/src-tauri")
try {
  Invoke-Checked "Rust lockfile sync" { cargo check }
  Invoke-Checked "Rust check" { cargo check --locked }
} finally {
  Pop-Location
}

# --- 3. Build EXE + installer before commit/push/tag/release ---
if (-not $SkipBuild) {
  & (Join-Path $PSScriptRoot "build-windows-release.ps1") -Version $Version
  if ($LASTEXITCODE -ne 0) { throw "Windows release build failed ($LASTEXITCODE)" }
}

$installer = Join-Path $repoRoot "release/wmole-$Version-setup.exe"
$exe       = Join-Path $repoRoot "dist/wmole.exe"
foreach ($p in @($installer, $exe)) {
  if (-not (Test-Path $p)) { throw "Missing artifact: $p" }
}

# --- 3.5 Commit and push verified source only ---
if (-not $SkipPush) {
  $sourcePaths = @(
    ".github", ".gitignore", "README.md", "requirements.txt", "mole.py", "tests",
    "gui/package.json", "gui/package-lock.json", "gui/src", "gui/src-tauri/Cargo.toml",
    "gui/src-tauri/Cargo.lock", "gui/src-tauri/tauri.conf.json", "gui/src-tauri/src",
    "gui/src-tauri/capabilities", "installer", "scripts", "index.html", "docs"
  )
  & git add -- @sourcePaths
  if ($LASTEXITCODE -ne 0) { throw "git add failed ($LASTEXITCODE)" }
  git diff --cached --quiet
  if ($LASTEXITCODE -eq 0) {
    Write-Host "   no changes to commit"
  } elseif ($LASTEXITCODE -eq 1) {
    & git commit -m "release: $tag"
    if ($LASTEXITCODE -ne 0) { throw "git commit failed ($LASTEXITCODE)" }
  } else {
    throw "git diff failed ($LASTEXITCODE)"
  }
  & git push
  if ($LASTEXITCODE -ne 0) { throw "git push failed ($LASTEXITCODE)" }
}

# --- 4. Resolve release notes ---
if ($NotesFile -and (Test-Path $NotesFile)) {
  $Notes = Get-Content $NotesFile -Raw
}
if (-not $Notes) {
  $Notes = "Automated release $tag."
}
$notesPath = Join-Path $env:TEMP "wmole-release-$Version.md"
$Notes | Set-Content $notesPath -Encoding UTF8

# --- 4.5 SHA-256 üret (in-app updater doğrulaması için) ---
$shaPath = "$installer.sha256"
$hash = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLower()
"$hash  wmole-$Version-setup.exe" | Set-Content $shaPath -Encoding ASCII
Write-Host "   sha256: $hash"

# --- 5. Create GitHub release (replace if tag exists) ---
& git tag -f $tag
if ($LASTEXITCODE -ne 0) { throw "git tag failed ($LASTEXITCODE)" }
& git push origin $tag --force-with-lease
if ($LASTEXITCODE -ne 0) { throw "tag push failed ($LASTEXITCODE)" }

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$null = gh release view $tag 2>&1
$exists = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $prevEAP
if ($exists) {
  Write-Host "   release $tag exists; replacing verified assets"
  & gh release upload $tag $installer $shaPath $exe --clobber
  if ($LASTEXITCODE -ne 0) { throw "release asset upload failed ($LASTEXITCODE)" }
  & gh release edit $tag --title "wmole $tag" --notes-file $notesPath
  if ($LASTEXITCODE -ne 0) { throw "release edit failed ($LASTEXITCODE)" }
} else {
  $ghArgs = @("release", "create", $tag, $installer, $shaPath, $exe,
              "--title", "wmole $tag", "--notes-file", $notesPath)
  if ($Prerelease) { $ghArgs += "--prerelease" }
  & gh @ghArgs
  if ($LASTEXITCODE -ne 0) { throw "release create failed ($LASTEXITCODE)" }
}

Write-Host ""
Write-Host "==> Done." -ForegroundColor Green
Write-Host "    Site changelog will pick up $tag on next page load (GitHub API)."
Write-Host "    Live:  https://wmole.vercel.app/#changelog"
