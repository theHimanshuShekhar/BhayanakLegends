# Setup Commands — run in order, in a real terminal

These are the commands I cannot run for you (they need your credentials /
interactive approval). Run them top to bottom in a terminal in
`/home/hshekhar/code/BhayanakLegends`.

## 1. Install Linux build dependencies (needed for local dev/build in WSL)

```bash
sudo apt-get update
sudo apt-get install -y libwebkit2gtk-4.1-dev build-essential curl wget file libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
```

Verify: `pkg-config --modversion webkit2gtk-4.1` should print a version like `2.4x.x`.

## 2. Verify GitHub CLI is authenticated

```bash
gh auth status
```

If not logged in: `gh auth login` (follow the prompts).

## 3. Initialize the repo and make the first commit

```bash
git init -b main
git add .
git commit -m "feat: initial tauri app with commit-driven auto-update"
```

## 4. Create the GitHub repo and push

Replace `YOUR-USERNAME` with your GitHub username (or use an org):

```bash
git init -b main
git add .
git commit -m "feat: initial tauri app with commit-driven auto-update"
gh repo create BhayanakLegends --public --source=. --remote=origin --push
```

> **The repo must be public.** GitHub Pages is not available for private repos
> on the free plan, and the app's update endpoint must be publicly reachable
> anyway (installed apps download it with no credentials).
>
> If you already created it as private, flip it:
> `gh repo edit theHimanshuShekhar/BhayanakLegends --visibility public`

## 5. Add the updater signing secrets

```bash
gh secret set TAURI_SIGNING_PRIVATE_KEY < ~/.tauri/bhayanaklegends.key
gh secret set TAURI_SIGNING_PRIVATE_KEY_PASSWORD --body "changeme"
```

> The password is currently `changeme` — change it before any real release.
> See README "Important notes" for how to rotate keys.

## 6. Enable GitHub Pages (Actions source)

> Requires the repo to be **public** (free plan). If you get HTTP 422
> "Your current plan does not support GitHub Pages", flip visibility first:
> `gh repo edit theHimanshuShekhar/BhayanakLegends --visibility public`

Try the API first:

```bash
gh api repos/theHimanshuShekhar/BhayanakLegends/pages -f build_type=workflow
```

If it errors, do it manually: repo Settings → Pages → Source: **GitHub Actions**.

## 7. Trigger the first build and watch it

```bash
git push origin main
gh run watch
```

Wait for both `build` jobs (windows + linux) and the `publish` job to finish.
When green, the app is live at
`https://<your-username>.github.io/BhayanakLegends/latest.json`.

## 8. Verify end to end (optional, local)

```bash
export PATH="$HOME/.cargo/bin:$PATH"
export TAURI_SIGNING_PRIVATE_KEY="$(cat ~/.tauri/bhayanaklegends.key)"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="changeme"
pnpm tauri build
ls src-tauri/target/release/bundle/appimage/*.AppImage.sig
```

A local build also lets you test the update flow: install version A locally,
push a commit to main, then launch the old build and click "Check for updates".

## 9. Optional: use your own signing key password

```bash
pnpm tauri signer generate --ci -p "YOUR-PASSWORD" -w ~/.tauri/bhayanaklegends.key
cat ~/.tauri/bhayanaklegends.key.pub
```

Then: paste the new pubkey into `plugins.updater.pubkey` in
`src-tauri/tauri.conf.json`, and re-run step 5 with `YOUR-PASSWORD`.
