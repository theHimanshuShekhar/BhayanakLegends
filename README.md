# BhayanakLegends

Tauri 2.x desktop app (Windows 11 primary target, Linux supported) with auto-update driven by the latest commit on `main`.

## How auto-update works

Every push to `main` triggers `.github/workflows/update.yml`:

1. Builds the app for Windows (NSIS) and Linux (AppImage) with a version derived from the commit count (`0.1.<commit-count>`).
2. Signs the updater artifacts with the Tauri signing key.
3. Publishes `latest.json` + installers to GitHub Pages, replacing the previous build (rolling "latest").
4. The app checks `https://<owner>.github.io/<repo>/latest.json` on launch and via the "Check for updates" button.

## Local development

```sh
pnpm install
pnpm tauri dev
```

Local build (requires signing keys in env to produce `.sig` files):

```sh
export TAURI_SIGNING_PRIVATE_KEY="$(cat ~/.tauri/bhayanaklegends.key)"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="changeme"
pnpm tauri build
```

## One-time setup

1. Create the GitHub repo **public** and push (Pages isn't available for private repos on the free plan; see `docs/SETUP_COMMANDS.md` for the ordered commands).
2. Add secrets `TAURI_SIGNING_PRIVATE_KEY` (content of `~/.tauri/bhayanaklegends.key`) and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`.
3. Enable GitHub Pages in repo Settings → Pages → source **GitHub Actions** (or run the `gh api` command in the setup file).
4. Push to `main`. The first workflow run publishes version `0.1.<N>`.

## Important notes

- **The signing private key is irreplaceable** — losing it (or its password) means installed apps can never update. Back it up. The current password is `changeme`; regenerate with your own password before any real release:
  `pnpm tauri signer generate --ci -p <your-password> -w ~/.tauri/bhayanaklegends.key`, then copy the new `~/.tauri/bhayanaklegends.key.pub` content into `plugins.updater.pubkey` in `src-tauri/tauri.conf.json`, and re-set both secrets.
- Version comes from the commit count on `main`, so it is monotonic. A force-push/reset of `main` can lower it — the updater refuses downgrades, so affected users would stay on the older version.
- The updater endpoint in `src-tauri/tauri.conf.json` is a placeholder; CI rewrites it to the actual Pages URL before building.
- Windows installers are not Authenticode-signed, so SmartScreen may warn. Code-signing certs are a separate concern from the updater.