use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::io::{Read, Write};
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter, Manager};

const GH_REPO: &str = "palamut62/wmole";
const UA: &str = "wmole-updater";
const RELEASE_URL_PREFIX: &str = "https://github.com/palamut62/wmole/releases/download/";

fn validate_release_url(url: &str, expected_suffix: &str) -> Result<(), String> {
    if url.starts_with(RELEASE_URL_PREFIX) && url.ends_with(expected_suffix) {
        Ok(())
    } else {
        Err("invalid-update-url".into())
    }
}

fn setup_asset_name(url: &str) -> Result<&str, String> {
    url.rsplit('/').next().filter(|name| name.ends_with("-setup.exe"))
        .ok_or_else(|| "invalid-update-asset-name".into())
}

fn file_sha256(path: &std::path::Path) -> Result<String, String> {
    let mut file = std::fs::File::open(path).map_err(|e| format!("disk: {e}"))?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let count = file.read(&mut buffer).map_err(|e| format!("disk: {e}"))?;
        if count == 0 { break; }
        digest.update(&buffer[..count]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

#[derive(Deserialize)]
struct GhAsset {
    name: String,
    browser_download_url: String,
    size: u64,
}

#[derive(Deserialize)]
struct GhRelease {
    tag_name: String,
    body: String,
    #[serde(default)]
    prerelease: bool,
    assets: Vec<GhAsset>,
}

#[derive(Serialize, Clone)]
pub struct UpdateInfo {
    available: bool,
    current: String,
    latest: String,
    notes: String,
    download_url: String,
    sha256_url: String,
    size: u64,
}

#[derive(Serialize, Clone)]
struct Progress {
    downloaded: u64,
    total: u64,
    pct: u8,
}

/// GitHub Releases API ile en son sürümü kontrol et.
/// Hata = ağ/parse sorunu (UI'de toast'lanır).
#[tauri::command]
pub async fn check_update(app: AppHandle) -> Result<UpdateInfo, String> {
    let current = app.package_info().version.to_string();
    let url = format!("https://api.github.com/repos/{GH_REPO}/releases/latest");

    let rel: GhRelease = reqwest::Client::new()
        .get(&url)
        .header("User-Agent", UA)
        .header("Accept", "application/vnd.github+json")
        .send()
        .await
        .map_err(|e| format!("network: {e}"))?
        .error_for_status()
        .map_err(|e| format!("http: {e}"))?
        .json()
        .await
        .map_err(|e| format!("parse: {e}"))?;

    let latest = rel.tag_name.trim_start_matches('v').to_string();

    // semver ile karşılaştır; parse edilemezse string eşitliğine düş.
    let newer = match (
        semver::Version::parse(&latest),
        semver::Version::parse(&current),
    ) {
        (Ok(l), Ok(c)) => l > c,
        _ => latest != current,
    };

    // -setup.exe asset'i + eşleşen .sha256 dosyası.
    let (download_url, size) = rel
        .assets
        .iter()
        .find(|a| a.name.ends_with("-setup.exe"))
        .map(|a| (a.browser_download_url.clone(), a.size))
        .unwrap_or((String::new(), 0));

    let sha256_url = rel
        .assets
        .iter()
        .find(|a| a.name.ends_with(".sha256"))
        .map(|a| a.browser_download_url.clone())
        .unwrap_or_default();

    Ok(UpdateInfo {
        available: newer && !rel.prerelease && !download_url.is_empty(),
        current,
        latest,
        notes: rel.body,
        download_url,
        sha256_url,
        size,
    })
}

/// Setup.exe'yi indir → ilerleme emit et → SHA-256 doğrula → dosya yolunu döndür.
#[tauri::command]
pub async fn download_update(
    app: AppHandle,
    url: String,
    sha256_url: String,
    total: u64,
) -> Result<String, String> {
    validate_release_url(&url, "-setup.exe")?;
    validate_release_url(&sha256_url, ".sha256")?;
    let asset_name = setup_asset_name(&url)?.to_string();
    let dir = app.path().temp_dir().map_err(|e| format!("disk: {e}"))?;
    let nonce = SystemTime::now().duration_since(UNIX_EPOCH)
        .map_err(|e| format!("clock: {e}"))?.as_nanos();
    let target = dir.join(format!("wmole-update-{nonce}-{}-{asset_name}", std::process::id()));

    let client = reqwest::Client::new();
    let resp = client
        .get(&url)
        .header("User-Agent", UA)
        .send()
        .await
        .map_err(|e| format!("network: {e}"))?
        .error_for_status()
        .map_err(|e| format!("http: {e}"))?;

    // yetersiz alan / izin hatası burada yakalanır
    let mut file = std::fs::OpenOptions::new().write(true).create_new(true)
        .open(&target).map_err(|e| format!("disk: {e}"))?;
    let mut hasher = Sha256::new();
    let mut downloaded: u64 = 0;
    let mut last_pct: u8 = 255;
    let mut stream = resp.bytes_stream();

    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| format!("stream: {e}"))?;
        file.write_all(&chunk).map_err(|e| format!("disk: {e}"))?; // disk dolu → hata
        hasher.update(&chunk);
        downloaded += chunk.len() as u64;
        let pct = if total > 0 {
            ((downloaded * 100 / total) as u8).min(100)
        } else {
            0
        };
        if pct != last_pct {
            last_pct = pct;
            let _ = app.emit(
                "update-progress",
                Progress {
                    downloaded,
                    total,
                    pct,
                },
            );
        }
    }
    file.flush().ok();
    drop(file);

    if total > 0 && downloaded != total {
        let _ = std::fs::remove_file(&target);
        return Err(format!("size-mismatch:{downloaded}:{total}"));
    }

    // SHA-256 doğrulama (bozuk/eksik indirme tespiti)
    let got = format!("{:x}", hasher.finalize());
    let expected_raw = client
        .get(&sha256_url)
        .header("User-Agent", UA)
        .send()
        .await
        .map_err(|e| format!("network: {e}"))?
        .text()
        .await
        .map_err(|e| format!("network: {e}"))?;
    // .sha256 formatı: "<hash>  wmole-X.Y.Z-setup.exe"
    let mut checksum_fields = expected_raw.split_whitespace();
    let expected = checksum_fields.next().unwrap_or("").to_lowercase();
    let checksum_name = checksum_fields.next().unwrap_or("").trim_start_matches('*');

    if expected.is_empty() || got != expected || checksum_name != asset_name {
        let _ = std::fs::remove_file(&target); // bozuk dosyayı sil
        return Err("checksum-or-asset-mismatch".into());
    }

    std::fs::write(target.with_extension("exe.sha256"), &expected)
        .map_err(|e| format!("disk: {e}"))?;

    Ok(target.to_string_lossy().to_string())
}

/// İndirilen Tauri NSIS setup.exe'yi sessizce çalıştır, uygulamayı kapat.
/// `/S` sessiz kurulum; NSIS şablonu çalışan örneği kapatır ve kurulum
/// sonrası uygulamayı yeniden başlatır.
#[tauri::command]
pub fn install_update(app: AppHandle, setup_path: String) -> Result<(), String> {
    let expected_dir = app
        .path()
        .temp_dir()
        .map_err(|e| format!("disk: {e}"))?;
    let requested = std::fs::canonicalize(&setup_path).map_err(|_| "setup-missing")?;
    let parent = requested.parent().ok_or("invalid-setup-path")?;
    let expected_dir = std::fs::canonicalize(expected_dir).map_err(|_| "setup-missing")?;
    let filename = requested.file_name().and_then(|name| name.to_str()).unwrap_or("");
    if parent != expected_dir || !filename.starts_with("wmole-update-") || !filename.ends_with("-setup.exe") {
        return Err("invalid-setup-path".into());
    }
    if !requested.is_file() {
        return Err("setup-missing".into());
    }
    let expected_hash = std::fs::read_to_string(requested.with_extension("exe.sha256"))
        .map_err(|_| "verification-missing")?;
    let actual_hash = file_sha256(&requested)?;
    if !actual_hash.eq_ignore_ascii_case(expected_hash.trim()) {
        return Err("checksum-changed-before-install".into());
    }
    std::process::Command::new(&requested)
        .arg("/S")
        .spawn()
        .map_err(|e| format!("spawn: {e}"))?; // kurulum başlatılamadı
    // Dosya kilidini bırak; installer kurup uygulamayı yeniden başlatacak.
    app.exit(0);
    Ok(())
}
