use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Mutex,
};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter, Manager};

const GH_REPO: &str = "umutc6230/wmole";
const UA: &str = "wmole-updater";
const RELEASE_URL_PREFIX: &str = "https://github.com/umutc6230/wmole/releases/download/";

/// Minisign (ed25519) public key — güncelleme paketlerinin gerçekliğini doğrular.
///
/// TODO: Buraya gerçek public key'i yaz. Üretmek için: `minisign -G -p wmole.pub -s wmole.key`
/// ardından `wmole.pub` dosyasının İKİNCİ satırını (base64 gövde, "RWQ..." ile başlar)
/// buraya kopyala. Secret key CI'da `MINISIGN_KEY` secret'ı olarak tutulur ve release
/// job'ı `minisign -S -s wmole.key -m wmole-X.Y.Z-setup.exe` ile `.minisig` üretir.
/// Detay: README "Güncelleme imzalama" bölümü.
///
/// Missing signing configuration blocks automatic installation.
const UPDATE_PUBKEY: &str = "RWQPLACEHOLDER00000000000000000000000000000000000000000";
const PUBKEY_PLACEHOLDER: &str = "RWQPLACEHOLDER00000000000000000000000000000000000000000";

fn pubkey_is_placeholder() -> bool {
    UPDATE_PUBKEY == PUBKEY_PLACEHOLDER || UPDATE_PUBKEY.trim().is_empty()
}

#[derive(Default)]
pub struct UpdateState(Mutex<Option<VerifiedUpdate>>);
struct VerifiedUpdate {
    path: PathBuf,
    sha256: String,
    signature: String,
}
static DOWNLOADING: AtomicBool = AtomicBool::new(false);
struct DownloadGuard;
impl Drop for DownloadGuard {
    fn drop(&mut self) {
        DOWNLOADING.store(false, Ordering::SeqCst);
    }
}
struct StagedFile {
    path: PathBuf,
    keep: bool,
}
impl Drop for StagedFile {
    fn drop(&mut self) {
        if !self.keep {
            let _ = std::fs::remove_file(&self.path);
            if let Some(parent) = self.path.parent() {
                let _ = std::fs::remove_dir(parent);
            }
        }
    }
}
fn require_signing_key() -> Result<(), String> {
    if pubkey_is_placeholder() {
        return Err("signature-not-configured".into());
    }
    Ok(())
}
fn verify_package(data: &[u8], sha256: &str, signature: &str) -> Result<(), String> {
    require_signing_key()?;
    if format!("{:x}", Sha256::digest(data)) != sha256 {
        return Err("package-changed".into());
    }
    let pk = minisign_verify::PublicKey::from_base64(UPDATE_PUBKEY)
        .map_err(|_| "invalid-signing-key")?;
    let sig = minisign_verify::Signature::decode(signature)
        .map_err(|_| "signature-verification-failed")?;
    pk.verify(data, &sig, false)
        .map_err(|_| "signature-verification-failed".into())
}
fn client() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(15))
        .timeout(Duration::from_secs(900))
        .build()
        .map_err(|e| e.to_string())
}

fn validate_release_url(url: &str, expected_suffix: &str) -> Result<(), String> {
    if url.starts_with(RELEASE_URL_PREFIX) && url.ends_with(expected_suffix) {
        Ok(())
    } else {
        Err("invalid-update-url".into())
    }
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
    sig_url: String,
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

    let rel: GhRelease = client()?
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

    // -setup.exe asset'i + AYNI dosyaya ait .sha256 / .minisig yardımcı dosyaları.
    // (Eskiden ilk ".sha256" ile biten asset alınıyordu; birden fazla asset olan
    //  release'lerde yanlış dosyanın hash'i çekilebiliyordu — adı setup'tan türetiyoruz.)
    let setup = rel.assets.iter().find(|a| a.name.ends_with("-setup.exe"));
    let (setup_name, download_url, size) = match setup {
        Some(a) => (a.name.clone(), a.browser_download_url.clone(), a.size),
        None => (String::new(), String::new(), 0),
    };

    let find_named = |suffix: &str| -> String {
        if setup_name.is_empty() {
            return String::new();
        }
        let want = format!("{setup_name}{suffix}");
        rel.assets
            .iter()
            .find(|a| a.name == want)
            .map(|a| a.browser_download_url.clone())
            .unwrap_or_default()
    };
    let sha256_url = find_named(".sha256");
    let sig_url = find_named(".minisig");

    // sha256 dosyası yoksa indirme zaten "invalid-update-url" ile patlardı;
    // güncellemeyi "mevcut" göstermek yerine baştan eleriz.
    Ok(UpdateInfo {
        available: newer && !rel.prerelease && !download_url.is_empty() && !sha256_url.is_empty(),
        current,
        latest,
        notes: rel.body,
        download_url,
        sha256_url,
        sig_url,
        size,
    })
}

/// Setup.exe'yi indir → ilerleme emit et → SHA-256 (ucuz erken eleme) →
/// minisign/ed25519 imza doğrula → dosya yolunu döndür.
#[tauri::command]
pub async fn download_update(
    app: AppHandle,
    url: String,
    sha256_url: String,
    sig_url: String,
    total: u64,
) -> Result<String, String> {
    require_signing_key()?;
    if DOWNLOADING.swap(true, Ordering::SeqCst) {
        return Err("update-busy".into());
    }
    let _download_guard = DownloadGuard;
    if sig_url.is_empty() {
        return Err("signature-missing".into());
    }
    if total == 0 || total > 512 * 1024 * 1024 {
        return Err("invalid-package-size".into());
    }
    validate_release_url(&url, "-setup.exe")?;
    validate_release_url(&sha256_url, ".sha256")?;
    if !sig_url.is_empty() {
        validate_release_url(&sig_url, ".minisig")?;
    }
    if sha256_url != format!("{url}.sha256") || sig_url != format!("{url}.minisig") {
        return Err("invalid-update-url".into());
    }
    let root = app
        .path()
        .app_cache_dir()
        .map_err(|e| format!("disk: {e}"))?
        .join("updates");
    std::fs::create_dir_all(&root).map_err(|e| format!("disk: {e}"))?;
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_nanos();
    let dir = root.join(format!("{}-{nonce}", std::process::id()));
    std::fs::create_dir(&dir).map_err(|e| format!("disk: {e}"))?;
    let target = dir.join("setup.exe");
    let mut staged = StagedFile {
        path: target.clone(),
        keep: false,
    };

    let client = client()?;
    let resp = client
        .get(&url)
        .header("User-Agent", UA)
        .send()
        .await
        .map_err(|e| format!("network: {e}"))?
        .error_for_status()
        .map_err(|e| format!("http: {e}"))?;

    // yetersiz alan / izin hatası burada yakalanır
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&target)
        .map_err(|e| format!("disk: {e}"))?;
    let mut hasher = Sha256::new();
    let mut downloaded: u64 = 0;
    let mut last_pct: u8 = 255;
    let mut stream = resp.bytes_stream();

    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| format!("stream: {e}"))?;
        if downloaded + chunk.len() as u64 > total {
            return Err("size-mismatch".into());
        }
        file.write_all(&chunk).map_err(|e| format!("disk: {e}"))?; // disk dolu → hata
        hasher.update(&chunk);
        downloaded += chunk.len() as u64;
        let pct = if total > 0 {
            (downloaded * 100 / total).min(100) as u8
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
    file.sync_all().map_err(|e| format!("disk: {e}"))?;
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
    let expected = expected_raw
        .split_whitespace()
        .next()
        .unwrap_or("")
        .to_lowercase();

    if expected.is_empty() || got != expected {
        let _ = std::fs::remove_file(&target); // bozuk dosyayı sil
        return Err(format!("checksum-mismatch:{got}:{expected}"));
    }

    let sig_text = client
        .get(&sig_url)
        .header("User-Agent", UA)
        .send()
        .await
        .map_err(|e| format!("network: {e}"))?
        .error_for_status()
        .map_err(|e| format!("http: {e}"))?
        .text()
        .await
        .map_err(|e| format!("network: {e}"))?;
    let data = std::fs::read(&target).map_err(|e| format!("disk: {e}"))?;
    verify_package(&data, &got, &sig_text)?;
    let verified = VerifiedUpdate {
        path: std::fs::canonicalize(&target).map_err(|e| e.to_string())?,
        sha256: got,
        signature: sig_text,
    };
    let state = app.state::<UpdateState>();
    let old = state.0.lock().map_err(|e| e.to_string())?.replace(verified);
    if let Some(old) = old {
        let _ = std::fs::remove_file(&old.path);
        if let Some(parent) = old.path.parent() {
            let _ = std::fs::remove_dir(parent);
        }
    }
    staged.keep = true;
    Ok(target.to_string_lossy().to_string())
}

/// İndirilen Tauri NSIS setup.exe'yi sessizce çalıştır, uygulamayı kapat.
/// `/S` sessiz kurulum; NSIS şablonu çalışan örneği kapatır ve kurulum
/// sonrası uygulamayı yeniden başlatır.
#[tauri::command]
pub fn install_update(app: AppHandle, setup_path: String) -> Result<(), String> {
    require_signing_key()?;
    let state = app.state::<UpdateState>();
    let verified = state
        .0
        .lock()
        .map_err(|e| e.to_string())?
        .take()
        .ok_or("package-not-verified")?;
    let requested = std::fs::canonicalize(&setup_path).map_err(|_| "setup-missing")?;
    if requested != verified.path {
        return Err("invalid-setup-path".into());
    }
    let mut options = std::fs::OpenOptions::new();
    options.read(true);
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        options.share_mode(1); // deny writes/deletion until CreateProcess opens the verified file
    }
    let mut file = options.open(&requested).map_err(|e| format!("disk: {e}"))?;
    if file.metadata().map_err(|e| e.to_string())?.len() > 512 * 1024 * 1024 {
        return Err("invalid-package-size".into());
    }
    let mut data = Vec::new();
    file.read_to_end(&mut data).map_err(|e| e.to_string())?;
    verify_package(&data, &verified.sha256, &verified.signature)?;
    std::process::Command::new(&requested)
        .arg("/S")
        .spawn()
        .map_err(|e| format!("spawn: {e}"))?;
    drop(file);
    app.exit(0);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_foreign_release_urls() {
        assert!(validate_release_url("https://evil.test/setup.exe", "-setup.exe").is_err());
        assert!(validate_release_url(
            &format!("{RELEASE_URL_PREFIX}v1/wmole-setup.exe"),
            "-setup.exe"
        )
        .is_ok());
    }
    #[test]
    fn missing_key_cannot_authorize_a_package() {
        if pubkey_is_placeholder() {
            assert_eq!(
                verify_package(b"tampered", "hash", "sig"),
                Err("signature-not-configured".into())
            );
        }
    }
    #[test]
    fn staging_failure_removes_only_its_own_file() {
        let root = std::env::temp_dir().join(format!("wmole-stage-test-{}", std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        let path = root.join("fixture.exe");
        std::fs::write(&path, b"fixture").unwrap();
        {
            let _stage = StagedFile {
                path: path.clone(),
                keep: false,
            };
        }
        assert!(!path.exists());
    }
}
