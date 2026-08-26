// Companion window ownership.
use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use tauri::{LogicalSize, Manager, PhysicalPosition, PhysicalSize};

const NORMAL_MIN_SIZE: WindowSize = WindowSize {
    width: 980,
    height: 620,
};
const COMPACT_MIN_SIZE: WindowSize = WindowSize {
    width: 320,
    height: 180,
};
const CHAMP_SELECT_SIZE: WindowSize = WindowSize {
    width: 560,
    height: 380,
};
const IN_GAME_SIZE: WindowSize = WindowSize {
    width: 440,
    height: 240,
};
const IN_GAME_EXPANDED_SIZE: WindowSize = WindowSize {
    width: 720,
    height: 520,
};
const COMPANION_MARGIN: u32 = 24;

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Serialize)]
#[serde(tag = "mode", rename_all = "kebab-case")]
pub enum CompanionMode {
    Idle,
    ChampSelect,
    InGame { expanded: bool },
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct WindowSize {
    width: u32,
    height: u32,
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct NormalGeometry {
    position: (i32, i32),
    size: WindowSize,
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct CompanionWindowState {
    mode: CompanionMode,
    always_on_top: bool,
    translucent: bool,
    min_size: WindowSize,
    normal_geometry_saved: bool,
    normal_geometry: Option<NormalGeometry>,
    restore_geometry: bool,
}

impl Default for CompanionWindowState {
    fn default() -> Self {
        Self {
            mode: CompanionMode::Idle,
            always_on_top: false,
            translucent: false,
            min_size: NORMAL_MIN_SIZE,
            normal_geometry_saved: false,
            normal_geometry: None,
            restore_geometry: false,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct MonitorBounds {
    x: i32,
    y: i32,
    width: u32,
    height: u32,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize)]
pub struct CompanionSnapshot {
    mode: CompanionMode,
    always_on_top: bool,
    translucent: bool,
    expanded: bool,
}

fn reduce_companion_state(
    previous: CompanionWindowState,
    mode: CompanionMode,
) -> CompanionWindowState {
    let entering_live =
        matches!(previous.mode, CompanionMode::Idle) && !matches!(mode, CompanionMode::Idle);
    let leaving_live =
        !matches!(previous.mode, CompanionMode::Idle) && matches!(mode, CompanionMode::Idle);
    CompanionWindowState {
        mode,
        always_on_top: !matches!(mode, CompanionMode::Idle),
        translucent: matches!(mode, CompanionMode::InGame { .. }),
        min_size: if matches!(mode, CompanionMode::Idle) {
            NORMAL_MIN_SIZE
        } else {
            COMPACT_MIN_SIZE
        },
        normal_geometry_saved: if leaving_live {
            false
        } else {
            previous.normal_geometry_saved || entering_live
        },
        normal_geometry: if leaving_live {
            None
        } else {
            previous.normal_geometry
        },
        restore_geometry: leaving_live,
    }
}

fn clamp_window_position(
    position: (i32, i32),
    size: (u32, u32),
    bounds: MonitorBounds,
) -> (i32, i32) {
    let max_x = bounds
        .x
        .saturating_add(bounds.width.saturating_sub(size.0) as i32);
    let max_y = bounds
        .y
        .saturating_add(bounds.height.saturating_sub(size.1) as i32);
    (
        position.0.clamp(bounds.x, max_x),
        position.1.clamp(bounds.y, max_y),
    )
}

fn scaled_size(size: WindowSize, scale_factor: f64) -> PhysicalSize<u32> {
    PhysicalSize::new(
        (f64::from(size.width) * scale_factor).round().max(1.0) as u32,
        (f64::from(size.height) * scale_factor).round().max(1.0) as u32,
    )
}

fn compact_position(
    bounds: MonitorBounds,
    size: WindowSize,
    scale_factor: f64,
) -> PhysicalPosition<i32> {
    let physical = scaled_size(size, scale_factor);
    let margin = (f64::from(COMPANION_MARGIN) * scale_factor).round() as u32;
    let (x, y) = clamp_window_position(
        (
            bounds
                .x
                .saturating_add(bounds.width.saturating_sub(physical.width + margin) as i32),
            bounds.y.saturating_add(margin as i32),
        ),
        (physical.width, physical.height),
        bounds,
    );
    PhysicalPosition::new(x, y)
}

pub(crate) struct CompanionState(Mutex<CompanionWindowState>);

impl CompanionState {
    pub(crate) fn new() -> Self {
        Self(Mutex::new(CompanionWindowState::default()))
    }
}
fn window_error(error: impl std::fmt::Display) -> String {
    error.to_string()
}

fn monitor_bounds<R: tauri::Runtime>(
    window: &tauri::WebviewWindow<R>,
    position: PhysicalPosition<i32>,
    size: PhysicalSize<u32>,
) -> Result<(MonitorBounds, f64), String> {
    let monitor = window.current_monitor().map_err(window_error)?;
    if let Some(monitor) = monitor {
        return Ok((
            MonitorBounds {
                x: monitor.position().x,
                y: monitor.position().y,
                width: monitor.size().width,
                height: monitor.size().height,
            },
            monitor.scale_factor(),
        ));
    }
    Ok((
        MonitorBounds {
            x: position.x,
            y: position.y,
            width: size.width,
            height: size.height,
        },
        window.scale_factor().map_err(window_error)?,
    ))
}

fn capture_geometry<R: tauri::Runtime>(
    window: &tauri::WebviewWindow<R>,
) -> Result<(NormalGeometry, MonitorBounds, f64), String> {
    let position = window.outer_position().map_err(window_error)?;
    let size = window.inner_size().map_err(window_error)?;
    let (bounds, scale_factor) = monitor_bounds(window, position, size)?;
    Ok((
        NormalGeometry {
            position: (position.x, position.y),
            size: WindowSize {
                width: size.width,
                height: size.height,
            },
        },
        bounds,
        scale_factor,
    ))
}

fn companion_snapshot(state: CompanionWindowState) -> CompanionSnapshot {
    CompanionSnapshot {
        mode: state.mode,
        always_on_top: state.always_on_top,
        translucent: state.translucent,
        expanded: matches!(state.mode, CompanionMode::InGame { expanded: true }),
    }
}

#[tauri::command(rename = "set_live_companion_mode")]
pub fn set_live_mode(
    app: tauri::AppHandle,
    state: tauri::State<'_, CompanionState>,
    mode: CompanionMode,
) -> Result<CompanionSnapshot, String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "main window is unavailable".to_string())?;
    let mut guard = state.0.lock().map_err(window_error)?;
    let previous = *guard;
    let mut next = reduce_companion_state(previous, mode);

    if next.normal_geometry_saved && !previous.normal_geometry_saved {
        let (geometry, _, _) = capture_geometry(&window)?;
        next.normal_geometry = Some(geometry);
    }

    let (bounds, scale_factor) = {
        let position = window.outer_position().map_err(window_error)?;
        let size = window.inner_size().map_err(window_error)?;
        monitor_bounds(&window, position, size)?
    };

    match mode {
        CompanionMode::Idle => {
            window
                .set_min_size(Some(LogicalSize::new(
                    f64::from(NORMAL_MIN_SIZE.width),
                    f64::from(NORMAL_MIN_SIZE.height),
                )))
                .map_err(window_error)?;
            if let Some(geometry) = previous.normal_geometry {
                let restored_size = PhysicalSize::new(geometry.size.width, geometry.size.height);
                let restored_position = clamp_window_position(
                    geometry.position,
                    (restored_size.width, restored_size.height),
                    bounds,
                );
                window.set_size(restored_size).map_err(window_error)?;
                window
                    .set_position(PhysicalPosition::new(
                        restored_position.0,
                        restored_position.1,
                    ))
                    .map_err(window_error)?;
            }
            window.set_decorations(true).map_err(window_error)?;
            window.set_always_on_top(false).map_err(window_error)?;
        }
        CompanionMode::ChampSelect => {
            window
                .set_min_size(Some(LogicalSize::new(
                    f64::from(COMPACT_MIN_SIZE.width),
                    f64::from(COMPACT_MIN_SIZE.height),
                )))
                .map_err(window_error)?;
            let size = scaled_size(CHAMP_SELECT_SIZE, scale_factor);
            window.set_size(size).map_err(window_error)?;
            window
                .set_position(compact_position(bounds, CHAMP_SELECT_SIZE, scale_factor))
                .map_err(window_error)?;
            window.set_decorations(true).map_err(window_error)?;
            // This changes z-order only; deliberately do not call set_focus.
            window.set_always_on_top(true).map_err(window_error)?;
        }
        CompanionMode::InGame { expanded } => {
            window
                .set_min_size(Some(LogicalSize::new(
                    f64::from(COMPACT_MIN_SIZE.width),
                    f64::from(COMPACT_MIN_SIZE.height),
                )))
                .map_err(window_error)?;
            let target_size = if expanded {
                IN_GAME_EXPANDED_SIZE
            } else {
                IN_GAME_SIZE
            };
            window
                .set_size(scaled_size(target_size, scale_factor))
                .map_err(window_error)?;
            if !matches!(
                previous.mode,
                CompanionMode::ChampSelect | CompanionMode::InGame { .. }
            ) {
                window
                    .set_position(compact_position(bounds, target_size, scale_factor))
                    .map_err(window_error)?;
            }
            window.set_decorations(false).map_err(window_error)?;
            window.set_always_on_top(true).map_err(window_error)?;
        }
    }

    if matches!(mode, CompanionMode::Idle) {
        next.normal_geometry = None;
    }
    *guard = next;
    Ok(companion_snapshot(next))
}
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn companion_transition_replays_idle_champ_select_game_idle() {
        let initial = CompanionWindowState::default();
        let champ_select = reduce_companion_state(initial, CompanionMode::ChampSelect);
        assert_eq!(champ_select.mode, CompanionMode::ChampSelect);
        assert!(champ_select.always_on_top);
        assert!(!champ_select.translucent);
        assert!(champ_select.normal_geometry_saved);
        assert_eq!(champ_select.normal_geometry, None);
        let in_game =
            reduce_companion_state(champ_select, CompanionMode::InGame { expanded: false });
        assert_eq!(in_game.mode, CompanionMode::InGame { expanded: false });
        assert!(in_game.always_on_top);
        assert!(in_game.translucent);
        assert_eq!(in_game.min_size, COMPACT_MIN_SIZE);
        assert!(in_game.normal_geometry_saved);
        let expanded = reduce_companion_state(in_game, CompanionMode::InGame { expanded: true });
        assert_eq!(expanded.mode, CompanionMode::InGame { expanded: true });
        assert!(expanded.always_on_top);
        assert!(expanded.translucent);

        let idle = reduce_companion_state(expanded, CompanionMode::Idle);
        assert_eq!(idle.mode, CompanionMode::Idle);
        assert!(!idle.always_on_top);
        assert!(!idle.translucent);
        assert!(!idle.normal_geometry_saved);
        assert!(idle.restore_geometry);
    }

    #[test]
    fn companion_transition_does_not_overwrite_saved_geometry() {
        let champ_select = reduce_companion_state(
            CompanionWindowState {
                normal_geometry_saved: true,
                ..CompanionWindowState::default()
            },
            CompanionMode::ChampSelect,
        );
        assert!(champ_select.normal_geometry_saved);

        let next = reduce_companion_state(champ_select, CompanionMode::InGame { expanded: false });
        assert!(next.normal_geometry_saved);
    }

    #[test]
    fn bounds_keep_restored_window_reachable() {
        let bounds = MonitorBounds {
            x: 1920,
            y: 0,
            width: 2560,
            height: 1440,
        };
        assert_eq!(
            clamp_window_position((-2000, -500), (1280, 820), bounds),
            (1920, 0)
        );
        assert_eq!(
            clamp_window_position((4300, 900), (1280, 820), bounds),
            (3200, 620)
        );
    }
}
