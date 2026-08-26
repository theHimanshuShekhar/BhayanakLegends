[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$InstallerPath,
  [Parameter(Mandatory = $true)][string]$InstallRoot,
  [Parameter(Mandatory = $true)][string]$DebugPort,
  [Parameter(Mandatory = $true)][string]$StatePath,
  [Parameter(Mandatory = $true)][string]$FlipFile,
  [Parameter(Mandatory = $true)][string]$HigherVersion,
  [Parameter(Mandatory = $true)][string]$RejectedVersion
)

# Proves the full signed-updater lifecycle against the lower-version install
# produced from $InstallerPath:
#   1. update-available: the app sees the fixture's real signed higher-version
#      offer and clicks the existing "Install update" action. The Windows
#      updater plugin writes the downloaded installer (the signed NSIS setup
#      .exe itself, served directly with no zip wrapping) into a temp file
#      named "<app>-<version>-installer.exe", spawns it, and calls
#      std::process::exit(0) before the JS promise resolves (no /R flag is
#      passed), so the app exits on its own; this harness waits for that exit
#      and then for the detached installer process to finish.
#   2. updated: the relaunched app must report the higher version, an
#      authenticated sidecar reconnection, and a durable Findings Pack.
#   3. invalid: after the harness creates $FlipFile, the fixture offers a
#      higher version whose signature does not match its bytes; the app must
#      reject it and leave the installed executable byte-for-byte unchanged.

$ErrorActionPreference = "Stop"
$state = [ordered]@{
  installer         = $InstallerPath
  install_root      = $InstallRoot
  debug_port        = [int]$DebugPort
  higher_version    = $HigherVersion
  rejected_version  = $RejectedVersion
  phases            = @()
  owned_sidecars    = @()
  errors            = @()
}

function Save-State {
  $state | ConvertTo-Json -Depth 8 | Set-Content -Path $StatePath -Encoding UTF8
}

function Get-Sidecars {
  @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -like "bhayanak-legends-sidecar*" } |
      ForEach-Object { [int]$_.ProcessId })
}

function Wait-Exit([int]$ProcessId, [int]$TimeoutSeconds = 20) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { return $true }
    Start-Sleep -Milliseconds 250
  } while ((Get-Date) -lt $deadline)
  return $false
}

function Wait-ProcessGoneByName([string]$NameLike, [int]$TimeoutSeconds) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like $NameLike })
    if ($running.Count -eq 0) { return $true }
    Start-Sleep -Milliseconds 500
  } while ((Get-Date) -lt $deadline)
  return $false
}

function Close-App([System.Diagnostics.Process]$App, [array]$BaselineSidecars) {
  $App.Refresh()
  if (-not $App.HasExited) {
    if (-not $App.CloseMainWindow()) {
      throw "packaged app did not expose a closable main window"
    }
    if (-not (Wait-Exit -ProcessId $App.Id)) {
      throw "packaged app did not close cleanly"
    }
  }
  Start-Sleep -Seconds 1
  $newSidecars = @(Get-Sidecars | Where-Object { $BaselineSidecars -notcontains $_ })
  $state.owned_sidecars += $newSidecars
  $survivors = @()
  foreach ($sidecar in $newSidecars) {
    if (-not (Wait-Exit -ProcessId $sidecar -TimeoutSeconds 10)) {
      $survivors += $sidecar
    }
  }
  if ($survivors.Count -gt 0) {
    $state.errors += "owned sidecars survived close: $($survivors -join ', ')"
    $survivors | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    throw "owned sidecar process survived its packaged app"
  }
}

try {
  New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
  $baseline = @(Get-Sidecars)
  $state.baseline_sidecars = $baseline
  $installerProcess = Start-Process -FilePath $InstallerPath -ArgumentList @("/S", "/D=$InstallRoot") -Wait -PassThru
  if ($installerProcess.ExitCode -ne 0) { throw "NSIS installer failed with exit code $($installerProcess.ExitCode)" }

  $appPath = Join-Path $InstallRoot "Bhayanak Legends.exe"
  if (-not (Test-Path $appPath)) {
    $candidate = Get-ChildItem -Path $InstallRoot -Filter "*.exe" -Recurse | Where-Object { $_.Name -notlike "uninstall*" } | Select-Object -First 1
    if (-not $candidate) { throw "packaged executable was not found under $InstallRoot" }
    $appPath = $candidate.FullName
  }
  $state.executable = $appPath

  $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$DebugPort"

  # --- Phase 1: the lower-version app discovers and installs the real signed higher-version update.
  $app1 = Start-Process -FilePath $appPath -WorkingDirectory (Split-Path $appPath) -PassThru
  try {
    & node tools/windows_packaged_smoke.mjs --phase update-available --debug-port $DebugPort --expected-version $HigherVersion
    if ($LASTEXITCODE -ne 0) { throw "webview assertion failed while installing the valid signed update" }
    $state.phases += [ordered]@{ name = "update-available"; result = "passed" }
  } catch {
    $state.phases += [ordered]@{ name = "update-available"; result = "failed"; error = $_.Exception.Message }
    # On the success path app1 self-exits via std::process::exit(0) inside
    # the updater plugin; on failure it is still running and must not leak.
    $app1.Refresh()
    if (-not $app1.HasExited) {
      $app1.CloseMainWindow() | Out-Null
      Start-Sleep -Seconds 1
      $app1.Refresh()
      if (-not $app1.HasExited) { Stop-Process -Id $app1.Id -Force -ErrorAction SilentlyContinue }
    }
    throw
  }
  Save-State

  if (-not (Wait-Exit -ProcessId $app1.Id -TimeoutSeconds 60)) {
    throw "packaged app did not exit to hand off to the signed-update installer"
  }
  # Best-effort hygiene: a hard process::exit(0) skips Drop-based cleanup, so
  # sweep any sidecar this instance owned before the next phase starts. This
  # does not assert the invariant (Close-App does that on every graceful-exit
  # phase below); it only prevents a leaked process from lingering.
  $strandedSidecars = @(Get-Sidecars | Where-Object { $baseline -notcontains $_ })
  if ($strandedSidecars.Count -gt 0) {
    $state.owned_sidecars += $strandedSidecars
    $strandedSidecars | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
  }
  # The plugin writes the downloaded setup .exe to a temp file named
  # "<app_name>-<version>-installer.exe" (app.package_info().name + version),
  # spawns it, and exits, so wait on that exact shape rather than the bundle
  # filename.
  if (-not (Wait-ProcessGoneByName -NameLike "*$HigherVersion*installer*" -TimeoutSeconds 120)) {
    throw "updater-spawned NSIS installer did not finish applying the signed update"
  }
  Start-Sleep -Seconds 1

  # --- Phase 2: the relaunched app must be the higher version with a healthy, reconnected sidecar.
  $app2 = Start-Process -FilePath $appPath -WorkingDirectory (Split-Path $appPath) -PassThru
  try {
    & node tools/windows_packaged_smoke.mjs --phase updated --debug-port $DebugPort
    if ($LASTEXITCODE -ne 0) { throw "webview assertion failed verifying the relaunched update" }
    $state.phases += [ordered]@{ name = "updated"; result = "passed" }
  } catch {
    $state.phases += [ordered]@{ name = "updated"; result = "failed"; error = $_.Exception.Message }
    throw
  } finally {
    Close-App -App $app2 -BaselineSidecars $baseline
  }
  Save-State

  $installedVersion = (Get-Item -Path $appPath).VersionInfo.ProductVersion
  if ($installedVersion -ne $HigherVersion) {
    throw "packaged executable reports version '$installedVersion' after relaunch; expected '$HigherVersion'"
  }
  $state.installed_version_after_update = $installedVersion
  $updatedHash = (Get-FileHash -Path $appPath).Hash
  Save-State

  # --- Phase 3: a real archive with a signature that does not match its bytes must be rejected.
  New-Item -ItemType File -Force -Path $FlipFile | Out-Null

  $app3 = Start-Process -FilePath $appPath -WorkingDirectory (Split-Path $appPath) -PassThru
  try {
    & node tools/windows_packaged_smoke.mjs --phase invalid --debug-port $DebugPort --expected-version $RejectedVersion
    if ($LASTEXITCODE -ne 0) { throw "webview assertion failed verifying mismatched-signature rejection" }
    $state.phases += [ordered]@{ name = "invalid"; result = "passed" }
  } catch {
    $state.phases += [ordered]@{ name = "invalid"; result = "failed"; error = $_.Exception.Message }
    throw
  } finally {
    Close-App -App $app3 -BaselineSidecars $baseline
  }
  Save-State

  $finalVersion = (Get-Item -Path $appPath).VersionInfo.ProductVersion
  if ($finalVersion -ne $HigherVersion) {
    throw "installed version changed after a rejected update: now '$finalVersion', expected '$HigherVersion'"
  }
  $finalHash = (Get-FileHash -Path $appPath).Hash
  if ($finalHash -ne $updatedHash) {
    throw "installed executable bytes changed after a rejected update"
  }
  $state.rejected_update_left_install_unchanged = $true
  $state.result = "passed"
  Save-State
} catch {
  $state.result = "failed"
  $state.errors += $_.Exception.Message
  Save-State
  throw
} finally {
  Remove-Item Env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS -ErrorAction SilentlyContinue
}
