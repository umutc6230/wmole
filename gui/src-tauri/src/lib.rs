use std::sync::Mutex;
use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Emitter, Manager, State,
};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

mod updater;

struct Sidecar(Mutex<Option<CommandChild>>);

#[tauri::command]
fn send_request(state: State<Sidecar>, line: String) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    let child = guard.as_mut().ok_or("sidecar not started")?;
    child
        .write((line + "\n").as_bytes())
        .map_err(|e| e.to_string())?;
    Ok(())
}

/// Mevcut uygulamayı yönetici (UAC) olarak yeniden başlat, sonra mevcut örneği kapat.
#[tauri::command]
fn relaunch_admin(app: tauri::AppHandle) -> Result<(), String> {
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    // PowerShell single-quoted strings escape a literal quote by doubling it.
    let exe_str = exe.to_string_lossy().replace('\'', "''");
    let status = std::process::Command::new("powershell")
        .args([
            "-WindowStyle",
            "Hidden",
            "-Command",
            &format!("try {{ Start-Process -FilePath '{}' -WindowStyle Hidden -Verb RunAs -ErrorAction Stop; exit 0 }} catch {{ exit 1 }}", exe_str),
        ])
        .status()
        .map_err(|e| e.to_string())?;
    if !status.success() {
        return Err("Yönetici izni verilmedi; uygulama açık kaldı".into());
    }
    app.exit(0);
    Ok(())
}

#[tauri::command]
fn restart_sidecar(app: tauri::AppHandle) -> Result<(), String> {
    let state = app.state::<Sidecar>();
    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    if guard.is_some() {
        return Ok(());
    }
    let sidecar = app
        .shell()
        .sidecar("wmole")
        .map_err(|e| e.to_string())?
        .args(["serve"]);
    let (mut rx, child) = sidecar.spawn().map_err(|e| e.to_string())?;
    guard.replace(child);
    drop(guard);

    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(bytes) => {
                    let text = String::from_utf8_lossy(&bytes);
                    for line in text.lines() {
                        if line.trim().is_empty() {
                            continue;
                        }
                        let _ = handle.emit("sidecar-event", line.to_string());
                    }
                }
                // Sidecar öldü: UI'daki bekleyen istekler sonsuza dek asılı kalmasın.
                CommandEvent::Terminated(_) => {
                    if let Ok(mut child) = handle.state::<Sidecar>().0.lock() {
                        child.take();
                    }
                    let _ = handle.emit("sidecar-exit", ());
                }
                _ => {}
            }
        }
    });

    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .manage(Sidecar(Mutex::new(None)))
        .manage(updater::UpdateState::default())
        .setup(|app| {
            restart_sidecar(app.handle().clone())?;

            // ── Sistem tepsisi (tray) ──
            let show = MenuItem::with_id(app, "show", "Göster", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Çıkış", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &quit])?;
            let _tray = TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .menu(&menu)
                .tooltip("wmole")
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            send_request,
            restart_sidecar,
            relaunch_admin,
            updater::check_update,
            updater::download_update,
            updater::install_update
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
