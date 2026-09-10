# Risk-accept transitive glib alert on Linux webview path

Dependabot #1 flags `glib 0.18.5` (`GHSA-wrw7-89jp-8q8g`, `VariantStrIter` UB, fixed in `0.20.0`) reached transitively via `tauri 2.11.5 → gtk 0.18 → glib 0.18`; we dismiss it as tolerable risk because the shipped Windows artifact never compiles the Linux `gtk`/`webkit2gtk` path and our Rust code never calls the affected iterator. Revisit on the next Tauri/wry bump that migrates to `gtk-rs-core 0.20+`.

## Considered Options

- **`cargo update` to latest tauri/wry** (rejected as fix): checked `wry 0.57.0`, still pins `gtk ^0.18` / `webkit2gtk =2.0.2`, so the `glib 0.18` line cannot clear yet.
- **Force `glib 0.20` via `[patch]`/override** (rejected): breaks `gtk 0.18` dependents; high churn for nil Windows risk.

## Consequences

- Alert stays dismissed with this justification until Tauri upstream moves off `gtk 0.18`; re-check `cargo tree -p glib` whenever `tauri`/`wry` is bumped.
