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

#[derive(Debug, Clone, Copy, PartialEq)]
struct AvailableMonitor {
    bounds: MonitorBounds,
    scale_factor: f64,
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct WindowGeometry {
    position: (i32, i32),
    size: WindowSize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum WindowEventKind {
    Resized,
    Moved,
    ScaleFactorChanged,
    MonitorTopologyChanged,
}

impl WindowEventKind {
    fn reclamps_live_window(self) -> bool {
        matches!(
            self,
            Self::Resized | Self::Moved | Self::ScaleFactorChanged | Self::MonitorTopologyChanged
        )
    }
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize)]
pub struct CompanionSnapshot {
    mode: CompanionMode,
    always_on_top: bool,
    translucent: bool,
    expanded: bool,
}

fn reduce_geometry_event(
    state: CompanionWindowState,
    event: WindowEventKind,
    geometry: WindowGeometry,
    bounds: MonitorBounds,
) -> Option<WindowGeometry> {
    if !matches!(state.mode, CompanionMode::Idle) && event.reclamps_live_window() {
        let clamped = clamp_geometry(geometry, bounds);
        (clamped != geometry).then_some(clamped)
    } else {
        None
    }
}

fn clamp_geometry(geometry: WindowGeometry, bounds: MonitorBounds) -> WindowGeometry {
    WindowGeometry {
        position: clamp_window_position(
            geometry.position,
            (geometry.size.width, geometry.size.height),
            bounds,
        ),
        ..geometry
    }
}

fn monitor_distance(position: (i32, i32), size: WindowSize, bounds: MonitorBounds) -> u64 {
    let left = i64::from(position.0);
    let top = i64::from(position.1);
    let right = left + i64::from(size.width);
    let bottom = top + i64::from(size.height);
    let monitor_left = i64::from(bounds.x);
    let monitor_top = i64::from(bounds.y);
    let monitor_right = monitor_left + i64::from(bounds.width);
    let monitor_bottom = monitor_top + i64::from(bounds.height);
    let horizontal = if right < monitor_left {
        monitor_left - right
    } else if left > monitor_right {
        left - monitor_right
    } else {
        0
    };
    let vertical = if bottom < monitor_top {
        monitor_top - bottom
    } else if top > monitor_bottom {
        top - monitor_bottom
    } else {
        0
    };
    horizontal
        .unsigned_abs()
        .saturating_add(vertical.unsigned_abs())
}

fn nearest_monitor(
    position: (i32, i32),
    size: WindowSize,
    monitors: &[AvailableMonitor],
) -> Option<AvailableMonitor> {
    monitors
        .iter()
        .copied()
        .min_by_key(|monitor| monitor_distance(position, size, monitor.bounds))
}

fn clamp_coordinate(value: i64) -> i32 {
    value.clamp(i64::from(i32::MIN), i64::from(i32::MAX)) as i32
}

fn clamp_window_position(
    position: (i32, i32),
    size: (u32, u32),
    bounds: MonitorBounds,
) -> (i32, i32) {
    let monitor_left = i64::from(bounds.x);
    let monitor_top = i64::from(bounds.y);
    let monitor_right = monitor_left + i64::from(bounds.width);
    let monitor_bottom = monitor_top + i64::from(bounds.height);
    let max_x = if size.0 >= bounds.width {
        monitor_left
    } else {
        monitor_right - i64::from(size.0)
    };
    let max_y = if size.1 >= bounds.height {
        monitor_top
    } else {
        monitor_bottom - i64::from(size.1)
    };
    let x = i64::from(position.0).clamp(monitor_left, max_x);
    let y = i64::from(position.1).clamp(monitor_top, max_y);
    (clamp_coordinate(x), clamp_coordinate(y))
}

fn scaled_dimension(value: u32, scale_factor: f64) -> u32 {
    let scaled = f64::from(value) * scale_factor;
    if !scaled.is_finite() {
        return u32::MAX;
    }
    scaled.round().clamp(1.0, f64::from(u32::MAX)) as u32
}

fn scaled_size(size: WindowSize, scale_factor: f64) -> PhysicalSize<u32> {
    PhysicalSize::new(
        scaled_dimension(size.width, scale_factor),
        scaled_dimension(size.height, scale_factor),
    )
}

fn compact_position(
    bounds: MonitorBounds,
    size: WindowSize,
    scale_factor: f64,
) -> PhysicalPosition<i32> {
    let physical = scaled_size(size, scale_factor);
    let margin = scaled_dimension(COMPANION_MARGIN, scale_factor);
    let (x, y) = clamp_window_position(
        (
            clamp_coordinate(
                i64::from(bounds.x)
                    + i64::from(
                        bounds
                            .width
                            .saturating_sub(physical.width.saturating_add(margin)),
                    ),
            ),
            clamp_coordinate(i64::from(bounds.y) + i64::from(margin)),
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

fn monitor_bounds<R: tauri::Runtime>(
    window: &tauri::WebviewWindow<R>,
    position: PhysicalPosition<i32>,
    size: PhysicalSize<u32>,
) -> Result<(MonitorBounds, f64), String> {
    if let Some(monitor) = window.current_monitor().map_err(window_error)? {
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

    let available = window.available_monitors().map_err(window_error)?;
    let monitors: Vec<_> = available
        .iter()
        .map(|monitor| AvailableMonitor {
            bounds: MonitorBounds {
                x: monitor.position().x,
                y: monitor.position().y,
                width: monitor.size().width,
                height: monitor.size().height,
            },
            scale_factor: monitor.scale_factor(),
        })
        .collect();
    if let Some(monitor) = nearest_monitor(
        (position.x, position.y),
        WindowSize {
            width: size.width,
            height: size.height,
        },
        &monitors,
    ) {
        return Ok((monitor.bounds, monitor.scale_factor));
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
    let size = window.outer_size().map_err(window_error)?;
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

fn reclamp_window<R: tauri::Runtime>(
    window: &tauri::WebviewWindow<R>,
    state: CompanionWindowState,
    event: WindowEventKind,
) -> Result<bool, String> {
    let position = window.outer_position().map_err(window_error)?;
    let size = window.outer_size().map_err(window_error)?;
    let (bounds, _) = monitor_bounds(window, position, size)?;
    let geometry = WindowGeometry {
        position: (position.x, position.y),
        size: WindowSize {
            width: size.width,
            height: size.height,
        },
    };
    let clamped = if matches!(state.mode, CompanionMode::Idle) {
        clamp_geometry(geometry, bounds)
    } else {
        reduce_geometry_event(state, event, geometry, bounds).unwrap_or(geometry)
    };
    if clamped == geometry {
        return Ok(false);
    }
    window
        .set_position(PhysicalPosition::new(
            clamped.position.0,
            clamped.position.1,
        ))
        .map_err(window_error)?;
    Ok(true)
}

pub(crate) fn handle_window_event<R: tauri::Runtime>(
    app: &tauri::AppHandle<R>,
    state: &CompanionState,
    label: &str,
    event: &tauri::WindowEvent,
) -> Result<(), String> {
    if label != "main" {
        return Ok(());
    }
    let event_kind = match event {
        tauri::WindowEvent::Resized(_) => WindowEventKind::Resized,
        tauri::WindowEvent::Moved(_) => WindowEventKind::Moved,
        tauri::WindowEvent::ScaleFactorChanged { .. } => WindowEventKind::ScaleFactorChanged,
        _ => return Ok(()),
    };
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "main window is unavailable".to_string())?;
    let guard = state.0.lock().map_err(window_error)?;
    if matches!(guard.mode, CompanionMode::Idle) {
        return Ok(());
    }
    reclamp_window(&window, *guard, event_kind)?;
    Ok(())
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
        let size = window.outer_size().map_err(window_error)?;
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
    reclamp_window(&window, next, WindowEventKind::MonitorTopologyChanged).map_err(window_error)?;
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

    #[test]
    fn oversized_window_is_anchored_at_monitor_origin() {
        let bounds = MonitorBounds {
            x: -1920,
            y: -100,
            width: 1280,
            height: 720,
        };
        assert_eq!(
            clamp_window_position((400, 400), (1920, 1080), bounds),
            (-1920, -100)
        );
    }

    #[test]
    fn nearest_monitor_is_selected_when_current_monitor_disappears() {
        let monitors = [
            AvailableMonitor {
                bounds: MonitorBounds {
                    x: -1920,
                    y: 0,
                    width: 1920,
                    height: 1080,
                },
                scale_factor: 1.0,
            },
            AvailableMonitor {
                bounds: MonitorBounds {
                    x: 0,
                    y: 0,
                    width: 2560,
                    height: 1440,
                },
                scale_factor: 1.5,
            },
        ];
        let selected = nearest_monitor(
            (2500, 100),
            WindowSize {
                width: 440,
                height: 240,
            },
            &monitors,
        );
        assert_eq!(selected, Some(monitors[1]));
    }

    #[test]
    fn geometry_events_reclamp_live_windows_once_and_ignore_idle() {
        let live = CompanionWindowState {
            mode: CompanionMode::InGame { expanded: false },
            ..CompanionWindowState::default()
        };
        let bounds = MonitorBounds {
            x: 0,
            y: 0,
            width: 1280,
            height: 720,
        };
        let outside = WindowGeometry {
            position: (1200, 600),
            size: WindowSize {
                width: 440,
                height: 240,
            },
        };
        for event in [
            WindowEventKind::Resized,
            WindowEventKind::Moved,
            WindowEventKind::ScaleFactorChanged,
            WindowEventKind::MonitorTopologyChanged,
        ] {
            assert_eq!(
                reduce_geometry_event(live, event, outside, bounds),
                Some(WindowGeometry {
                    position: (840, 480),
                    ..outside
                })
            );
            assert_eq!(
                reduce_geometry_event(
                    live,
                    event,
                    WindowGeometry {
                        position: (840, 480),
                        ..outside
                    },
                    bounds
                ),
                None
            );
        }
        assert_eq!(
            reduce_geometry_event(
                CompanionWindowState::default(),
                WindowEventKind::Resized,
                outside,
                bounds
            ),
            None
        );
    }

    #[test]
    fn geometry_uses_physical_size_for_scale_and_negative_coordinates() {
        assert_eq!(
            scaled_size(
                WindowSize {
                    width: 440,
                    height: 240,
                },
                1.5,
            ),
            PhysicalSize::new(660, 360)
        );
        let geometry = WindowGeometry {
            position: (-2500, -700),
            size: WindowSize {
                width: 980,
                height: 620,
            },
        };
        assert_eq!(
            clamp_geometry(
                geometry,
                MonitorBounds {
                    x: -1920,
                    y: -1080,
                    width: 1920,
                    height: 1080,
                },
            )
            .position,
            (-1920, -700)
        );
    }
}
