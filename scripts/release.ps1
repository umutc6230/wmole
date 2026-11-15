param(
  [Parameter(Mandatory=$true)][string]$Version,
  [string]$Notes = "",
  [string]$NotesFile = "",
  [switch]$Prerelease,
  [switch]$SkipPush,
  [switch]$SkipBuild
)

# wmole one-shot release pipeline:
#   1. bump the version everywhere it is declared
#   2. git add/commit/push
#   3. build wmole.exe (PyInstaller) + Tauri NSIS installer
#   4. sha256 (+ minisign signature when a key is configured)
#   5. gh release create with assets
# Changelog + web download button update themselves at runtime
# via the GitHub Releases API (see index.html: loadReleases).

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$tag = "v$Version"
Write-Host "==> Releasing wmole $tag" -ForegroundColor Cyan

# --- 1. Bump every declared version ---
# The updater compares the running version with the release tag, so a file left
# behind means the new build keeps offering itself as an update.
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Version must be X.Y.Z, got '$Version'" }
function Set-VersionLine([string]$RelPath, [string]$Pattern, [string]$Replacement) {
  $path = Join-Path $repoRoot $RelPath
  $text = [IO.File]::ReadAllText($path)
  $regex = [regex]$Pattern
  if (-not $regex.IsMatch($text)) { throw "version line not found in $RelPath" }
  # first match only: Cargo.toml / package.json also carry dependency versions
  [IO.File]::WriteAllText($path, $regex.Replace($text, $Replacement, 1))
}
Set-VersionLine "installer/wmole.iss"            '#define MyAppVersion "[^"]+"' "#define MyAppVersion `"$Version`""
Set-VersionLine "mole.py"                        '__version__ = "[^"]+"'        "__version__ = `"$Version`""
Set-VersionLine "gui/src-tauri/tauri.conf.json"  '"version": "[^"]+"'           "`"version`": `"$Version`""
Set-VersionLine "gui/src-tauri/Cargo.toml"       '(?m)^version = "[^"]+"'       "version = `"$Version`""
Push-Location (Join-Path $repoRoot "gui")
try {
  # package.json + package-lock.json together
  npm version $Version --no-git-tag-version --allow-same-version | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "npm version failed ($LASTEXITCODE)" }
} finally { Pop-Location }

# --- 2. Commit + push ---
if (-not $SkipPush) {
  git add -A
  if (git diff --cached --quiet) {
    Write-Host "   no changes to commit"
  } else {
    git commit -m "release: $tag" | Out-Null
  }
  git push
}

# --- 3. Build EXE + installer ---
if (-not $SkipBuild) {
  & (Join-Path $PSScriptRoot "build-windows-release.ps1") -Version $Version
}

$installer = Join-Path $repoRoot "release/wmole-$Version-setup.exe"
$exe       = Join-Path $repoRoot "dist/wmole.exe"
foreach ($p in @($installer, $exe)) {
  if (-not (Test-Path $p)) { throw "Missing artifact: $p" }
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

# --- 4.6 Minisign imzası (anahtar tanımlıysa) ---
# $env:WMOLE_MINISIGN_KEY = secret key dosyasının yolu. Bkz. gui/src-tauri/SIGNING.md
$sigPath = "$installer.minisig"
Remove-Item -LiteralPath $sigPath -Force -ErrorAction SilentlyContinue
$assets = @($installer, $shaPath, $exe)
if ($env:WMOLE_MINISIGN_KEY) {
  if (-not (Get-Command minisign -ErrorAction SilentlyContinue)) { throw "WMOLE_MINISIGN_KEY set but minisign is not on PATH" }
  minisign -S -s $env:WMOLE_MINISIGN_KEY -m $installer -x $sigPath
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $sigPath)) { throw "minisign signing failed" }
  $assets += $sigPath
  Write-Host "   signed: $sigPath"
} else {
  Write-Warning "WMOLE_MINISIGN_KEY not set: release is NOT signed (in-app updater falls back to SHA-256 only)."
}

# --- 5. Create GitHub release (replace if tag exists) ---
git tag -f $tag | Out-Null
git push origin $tag --force | Out-Null

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$null = gh release view $tag 2>&1
$exists = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $prevEAP
if ($exists) {
  Write-Host "   release $tag exists; deleting before recreate"
  gh release delete $tag --yes --cleanup-tag | Out-Null
  git push origin $tag --force | Out-Null
}

$ghArgs = @("release", "create", $tag) + $assets + @("--title", "wmole $tag", "--notes-file", $notesPath)
if ($Prerelease) { $ghArgs += "--prerelease" }
& gh @ghArgs

Write-Host ""
Write-Host "==> Done." -ForegroundColor Green
Write-Host "    Site changelog will pick up $tag on next page load (GitHub API)."
Write-Host "    Live:  https://wmole.vercel.app/#changelog"
