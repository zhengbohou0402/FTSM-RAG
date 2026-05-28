use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::Duration;

use tauri::{
    menu::{MenuBuilder, MenuItemBuilder},
    tray::TrayIconBuilder,
    Manager,
};

struct ServerState {
    process: Mutex<Option<Child>>,
    port: Mutex<u16>,
}

fn http_client() -> reqwest::blocking::Client {
    reqwest::blocking::Client::builder()
        .connect_timeout(Duration::from_secs(3))
        .timeout(Duration::from_secs(5))
        .build()
        .expect("build reqwest client")
}

fn find_free_port() -> u16 {
    let test = std::net::TcpListener::bind("127.0.0.1:8000");
    if test.is_ok() {
        return 8000;
    }
    match http_client().get("http://127.0.0.1:8000/api/health").send() {
        Ok(resp) if resp.status().is_success() => return 8000,
        _ => {}
    }
    portpicker::pick_unused_port().unwrap_or(18000)
}

fn backend_exe_path(resource_dir: Option<&PathBuf>) -> PathBuf {
    if let Some(res_dir) = resource_dir {
        let bundled = res_dir.join("python-backend").join("FTSM-RAG.exe");
        if bundled.exists() {
            log::info!("Using bundled backend: {:?}", bundled);
            return bundled;
        }
    }
    let dev_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .join("dist")
        .join("FTSM-RAG")
        .join("FTSM-RAG.exe");
    if dev_path.exists() {
        log::info!("Using dev backend: {:?}", dev_path);
        return dev_path;
    }
    // Resolve relative to the current exe's directory (production install)
    if let Ok(exe_path) = std::env::current_exe() {
        let exe_dir = exe_path.parent().unwrap_or_else(|| std::path::Path::new("."));
        for sub in &["python-backend", "resources/python-backend", "_resources/python-backend"] {
            let candidate = exe_dir.join(sub).join("FTSM-RAG.exe");
            if candidate.exists() {
                log::info!("Using sibling backend: {:?}", candidate);
                return candidate;
            }
        }
    }
    PathBuf::from("python-backend").join("FTSM-RAG.exe")
}

fn try_start_python_uvicorn(port: u16, repo_root: &std::path::Path) -> Option<Child> {
    let port_str = port.to_string();
    let uvicorn_args = [
        "-m",
        "uvicorn",
        "web_app:app",
        "--host",
        "127.0.0.1",
        "--port",
        port_str.as_str(),
        "--log-level",
        "warning",
    ];

    let mut python = Command::new("python");
    python
        .current_dir(repo_root)
        .env("FTSM_SERVER_ONLY", "1")
        .args(uvicorn_args.iter().copied());
    match python.spawn() {
        Ok(child) => {
            log::info!("Dev backend: python -m uvicorn (cwd={:?})", repo_root);
            return Some(child);
        }
        Err(e) => log::warn!("`python` not available for dev backend: {}", e),
    }

    let mut py = Command::new("py");
    py.current_dir(repo_root)
        .env("FTSM_SERVER_ONLY", "1")
        .arg("-3")
        .args(uvicorn_args.iter().copied());
    match py.spawn() {
        Ok(child) => {
            log::info!("Dev backend: py -3 -m uvicorn (cwd={:?})", repo_root);
            Some(child)
        }
        Err(e) => {
            log::warn!("`py -3` not available for dev backend: {}", e);
            None
        }
    }
}

fn start_backend(port: u16, exe_path: &std::path::Path) -> Option<Child> {
    log::info!("Starting backend: {:?} on port {}", exe_path, port);
    let mut cmd = Command::new(exe_path);
    cmd.env("FTSM_SERVER_ONLY", "1")
        .env("FTSM_PORT", port.to_string());
    // 调试构建：PyInstaller 后端在 dist/FTSM-RAG，默认同级 .env；指向仓库根 .env 与源码一致
    #[cfg(debug_assertions)]
    if let Some(repo_root) = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
    {
        cmd.env("FTSM_PROJECT_ROOT", repo_root.as_os_str());
    }
    let child = cmd.spawn().ok();
    if child.is_some() {
        log::info!("Backend started on port {}", port);
    } else {
        log::error!("Failed to start backend: {:?}", exe_path);
    }
    child
}

fn wait_for_server(url: &str, timeout_secs: u64) -> bool {
    let client = http_client();
    let deadline = std::time::Instant::now() + Duration::from_secs(timeout_secs);
    let health_url = format!("{}/api/health", url);

    while std::time::Instant::now() < deadline {
        match client.get(&health_url).send() {
            Ok(resp) if resp.status().is_success() => {
                log::info!("Server ready at {}", url);
                return true;
            }
            _ => std::thread::sleep(Duration::from_millis(300)),
        }
    }
    log::error!("Server failed to start within {}s", timeout_secs);
    false
}

#[tauri::command]
fn get_server_url(state: tauri::State<ServerState>) -> String {
    let port = state.port.lock().unwrap();
    format!("http://127.0.0.1:{}", *port)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let port = find_free_port();
    let server_url = format!("http://127.0.0.1:{}", port);

    let client = http_client();
    let server_already_running = client
        .get(format!("{}/api/health", server_url))
        .send()
        .map(|r| r.status().is_success())
        .unwrap_or(false);

    let child = if server_already_running {
        eprintln!("Server already running on port {}", port);
        None
    } else {
        #[cfg(debug_assertions)]
        let from_python = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(|p| p.parent())
            .and_then(|repo| try_start_python_uvicorn(port, repo.as_ref()));

        #[cfg(not(debug_assertions))]
        let from_python: Option<Child> = None;

        let c = if let Some(ch) = from_python {
            Some(ch)
        } else {
            let exe = backend_exe_path(None);
            log::info!("Fallback backend exe: {:?}", exe);
            start_backend(port, &exe)
        };
        if c.is_none() {
            eprintln!("WARNING: Could not start backend.");
        }
        if !wait_for_server(&server_url, 60) {
            eprintln!("WARNING: Server didn't start within 60s.");
        }
        c
    };

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _shortcut, event| {
                    if event.state == tauri_plugin_global_shortcut::ShortcutState::Pressed {
                        if let Some(window) = app.get_webview_window("main") {
                            if window.is_visible().unwrap_or(false) {
                                let _ = window.hide();
                            } else {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                    }
                })
                .build(),
        )
        .manage(ServerState {
            process: Mutex::new(child),
            port: Mutex::new(port),
        })
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // --- System Tray ---
            let show = MenuItemBuilder::with_id("show", "Show").build(app)?;
            let quit = MenuItemBuilder::with_id("quit", "Quit").build(app)?;
            let tray_menu = MenuBuilder::new(app).items(&[&show, &quit]).build()?;

            let _tray = TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("FTSM-RAG Assistant")
                .menu(&tray_menu)
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .build(app)?;

            // --- Global Shortcut: Alt+Space ---
            use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut};
            let shortcut = Shortcut::new(Some(Modifiers::ALT), Code::Space);
            app.global_shortcut().register(shortcut)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_server_url])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                // Hide to tray instead of closing
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

impl Drop for ServerState {
    fn drop(&mut self) {
        if let Ok(mut proc) = self.process.lock() {
            if let Some(ref mut child) = *proc {
                let _ = child.kill();
            }
        }
    }
}
