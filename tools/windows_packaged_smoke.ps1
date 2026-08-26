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

function Show-AppLogs {
  param(
    [Parameter(Mandatory = $true)][System.Diagnostics.Process]$App,
    [Parameter(Mandatory = $true)][string]$Context,
    [string]$AppStdoutLog,
    [string]$AppStderrLog,
    [string]$AppName
  )
  $App.Refresh()
  if ($App.HasExited) {
    Write-Output "packaged app state during ${Context}: exited (exit code $($App.ExitCode))"
  } else {
    Write-Output "packaged app state during ${Context}: still running"
  }
  foreach ($log in @($AppStdoutLog, $AppStderrLog)) {
    if (-not $log) { continue }
    if (Test-Path $log) {
      Write-Output "--- $log (last 40 lines) ---"
      if ((Get-Item $log).Length -gt 0) {
        Get-Content -Path $log -Tail 40 | ForEach-Object { Write-Output $_ }
      } else {
        Write-Output "(empty)"
      }
    } else {
      Write-Output "--- $log (absent) ---"
    }
  }
  # Crash forensics: surface recent Application-log entries tied to this
  # executable or generic crash reporters. Faulting module and exception
  # code lines are called out explicitly.
  if ($AppName) {
    try {
      $events = Get-WinEvent -FilterHashtable @{ LogName = "Application"; StartTime = (Get-Date).AddMinutes(-15) } `
        -ErrorAction SilentlyContinue |
        Where-Object {
          ($_.ProviderName -in @("Application Error", "Windows Error Reporting")) -or
          ($_.Message -and $_.Message -like "*$AppName*")
        } |
        Select-Object -First 10
      if ($events) {
        Write-Output "--- Application event log (last 15 min, matching '$AppName' or crash providers) ---"
        foreach ($event in $events) {
          Write-Output "[$($event.TimeCreated)] $($event.ProviderName) (id $($event.Id))"
          if ($event.Message) {
            $event.Message -split "`n" |
              Where-Object { $_ -match "faulting|exception|module" } |
              ForEach-Object { Write-Output "  $($_.Trim())" }
          } else {
            Write-Output "  (no message body)"
          }
        }
      } else {
        Write-Output "--- Application event log: no entries matching '$AppName' or crash providers in the last 15 minutes ---"
      }
    } catch {
      Write-Output "--- Application event log query failed: $($_.Exception.Message) ---"
    }
  }
}

function Invoke-WebviewAssertions {
  param(
    [Parameter(Mandatory = $true)][System.Diagnostics.Process]$App,
    [Parameter(Mandatory = $true)][string]$Phase,
    [Parameter(Mandatory = $true)][string]$DebugPort,
    [string]$ExpectedVersion,
    [int]$AppExitGraceSeconds = 0,
    [string]$AppStdoutLog,
    [string]$AppStderrLog,
    [string]$AppName
  )
  # Runs the webview assertions as a live child process so its stdout/stderr
  # stream straight into the step log, while polling the packaged app every
  # 250ms. An app that exits while assertions are still running is fatal
  # immediately (crash before the WebView2 host came up) — except in the
  # update-available phase, where the app legitimately self-exits during the
  # install handoff; there node gets a short grace window to conclude on its
  # own (it notices the CDP port going dark and exits 0) before this is
  # treated as a crash.
  $nodeArgs = @("tools/windows_packaged_smoke.mjs", "--phase", $Phase, "--debug-port", $DebugPort)
  if ($ExpectedVersion) { $nodeArgs += @("--expected-version", $ExpectedVersion) }
  $node = Start-Process -FilePath "node" -ArgumentList $nodeArgs -NoNewWindow -PassThru
  $appExitAt = $null
  try {
    while ($true) {
      $node.Refresh()
      if ($node.HasExited) { break }
      $App.Refresh()
      if ($App.HasExited) {
        $App.Refresh()
        Show-AppLogs -App $App -Context "phase '$Phase'" -AppStdoutLog $AppStdoutLog -AppStderrLog $AppStderrLog -AppName $AppName
        if ($AppExitGraceSeconds -le 0) {
          throw "packaged app exited while webview assertions were running (phase '$Phase', app exit code $($App.ExitCode))"
        }
        if (-not $appExitAt) {
          $appExitAt = Get-Date
        } elseif (((Get-Date) - $appExitAt).TotalSeconds -gt $AppExitGraceSeconds) {
          throw "packaged app exited and node did not conclude within ${AppExitGraceSeconds}s (phase '$Phase', app exit code $($App.ExitCode))"
        }
      }
      Start-Sleep -Milliseconds 250
    }
  } finally {
    # The node child must never outlive this block on any path.
    $node.Refresh()
    if (-not $node.HasExited) { Stop-Process -Id $node.Id -Force -ErrorAction SilentlyContinue }
  }
  if ($node.ExitCode -ne 0) {
    Show-AppLogs -App $App -Context "phase '$Phase' after node failure" -AppStdoutLog $AppStdoutLog -AppStderrLog $AppStderrLog -AppName $AppName
    throw "webview assertion failed during phase '$Phase' (node exit code $($node.ExitCode))"
  }
}

try {
  New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
  $baseline = @(Get-Sidecars)
  $state.baseline_sidecars = $baseline
  $installerProcess = Start-Process -FilePath $InstallerPath -ArgumentList @("/S", "/D=$InstallRoot") -Wait -PassThru
  if ($installerProcess.ExitCode -ne 0) { throw "NSIS installer failed with exit code $($installerProcess.ExitCode)" }

  # Tauri's productName controls the installer/display name, but the installed
  # executable keeps Cargo's binary name. Never fall back to the bundled
  # sidecar: doing so launches Python without the app-generated token and makes
  # every WebView assertion fail before CDP can open.
  $appPath = Join-Path $InstallRoot "bhayanak-legends.exe"
  if (-not (Test-Path $appPath)) {
    $candidates = @(Get-ChildItem -Path $InstallRoot -Filter "*.exe" -Recurse |
      Where-Object { $_.Name -notlike "uninstall*" -and $_.Name -notlike "*sidecar*" })
    if ($candidates.Count -ne 1) {
      $names = ($candidates | ForEach-Object { $_.FullName }) -join ", "
      throw "packaged app executable resolution was ambiguous: $names"
    }
    $appPath = $candidates[0].FullName
  }
  Write-Output "packaged app executable: $appPath"
  $state.executable = $appPath

  $appNameForDiagnostics = [System.IO.Path]::GetFileNameWithoutExtension($appPath)

  # Verify the exact sidecar copy laid down by NSIS before the app owns it.
  # Earlier probes exercise the build output; this closes the bundle/install
  # boundary and separates a transformed/wrong installed binary from the app's
  # process-spawn context.
  $installedSidecar = Get-ChildItem -Path $InstallRoot -Filter "bhayanak-legends-sidecar*.exe" -Recurse |
    Select-Object -First 1
  if (-not $installedSidecar) { throw "installed sidecar executable was not found under $InstallRoot" }
  $builtSidecar = Get-Item "src-tauri/binaries/bhayanak-legends-sidecar-x86_64-pc-windows-msvc.exe"
  $installedSidecarHash = (Get-FileHash $installedSidecar.FullName -Algorithm SHA256).Hash
  $builtSidecarHash = (Get-FileHash $builtSidecar.FullName -Algorithm SHA256).Hash
  Write-Output "installed sidecar: $($installedSidecar.FullName) size=$($installedSidecar.Length) sha256=$installedSidecarHash"
  Write-Output "built sidecar: $($builtSidecar.FullName) size=$($builtSidecar.Length) sha256=$builtSidecarHash"

  $installedProbeStdout = Join-Path $env:SMOKE_DIAGNOSTICS "installed-sidecar-probe-stdout.log"
  $installedProbeStderr = Join-Path $env:SMOKE_DIAGNOSTICS "installed-sidecar-probe-stderr.log"
  $env:BHAYANAK_TOKEN = "installed-sidecar-probe-" + ([guid]::NewGuid().ToString("N"))
  $installedProbe = Start-Process -FilePath $installedSidecar.FullName -PassThru `
    -RedirectStandardOutput $installedProbeStdout -RedirectStandardError $installedProbeStderr
  $installedProbeDeadline = (Get-Date).AddSeconds(12)
  do {
    Start-Sleep -Milliseconds 250
    $installedProbe.Refresh()
    $installedReady = (Test-Path $installedProbeStdout) -and
      (Select-String -Path $installedProbeStdout -Pattern '"type":\s*"ready"' -Quiet -ErrorAction SilentlyContinue)
  } while (-not $installedReady -and -not $installedProbe.HasExited -and (Get-Date) -lt $installedProbeDeadline)
  foreach ($log in @($installedProbeStdout, $installedProbeStderr)) {
    Write-Output "--- $log ---"
    if ((Test-Path $log) -and (Get-Item $log).Length -gt 0) {
      Get-Content $log | ForEach-Object { Write-Output $_ }
    } else {
      Write-Output "(empty or absent)"
    }
  }
  $state.installed_sidecar_probe = [ordered]@{
    ready = [bool]$installedReady
    installed_sha256 = $installedSidecarHash
    built_sha256 = $builtSidecarHash
    hashes_match = ($installedSidecarHash -eq $builtSidecarHash)
  }
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "bhayanak-legends-sidecar*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  $env:BHAYANAK_TOKEN = $null



  $app1StdoutLog = Join-Path $env:SMOKE_DIAGNOSTICS "app1-stdout.log"
  $app1StderrLog = Join-Path $env:SMOKE_DIAGNOSTICS "app1-stderr.log"
  $app1 = Start-Process -FilePath $appPath -WorkingDirectory (Split-Path $appPath) -PassThru `
    -RedirectStandardOutput $app1StdoutLog -RedirectStandardError $app1StderrLog
  try {
    # The app may legitimately self-exit mid-phase during install handoff;
    # give node a short grace window to notice the port going dark first.
    Invoke-WebviewAssertions -App $app1 -Phase "update-available" -DebugPort $DebugPort -ExpectedVersion $HigherVersion -AppExitGraceSeconds 15 `
      -AppStdoutLog $app1StdoutLog -AppStderrLog $app1StderrLog -AppName $appNameForDiagnostics
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
  $app2StdoutLog = Join-Path $env:SMOKE_DIAGNOSTICS "app2-stdout.log"
  $app2StderrLog = Join-Path $env:SMOKE_DIAGNOSTICS "app2-stderr.log"
  $app2 = Start-Process -FilePath $appPath -WorkingDirectory (Split-Path $appPath) -PassThru `
    -RedirectStandardOutput $app2StdoutLog -RedirectStandardError $app2StderrLog
  try {
    Invoke-WebviewAssertions -App $app2 -Phase "updated" -DebugPort $DebugPort `
      -AppStdoutLog $app2StdoutLog -AppStderrLog $app2StderrLog -AppName $appNameForDiagnostics
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

  $app3StdoutLog = Join-Path $env:SMOKE_DIAGNOSTICS "app3-stdout.log"
  $app3StderrLog = Join-Path $env:SMOKE_DIAGNOSTICS "app3-stderr.log"
  $app3 = Start-Process -FilePath $appPath -WorkingDirectory (Split-Path $appPath) -PassThru `
    -RedirectStandardOutput $app3StdoutLog -RedirectStandardError $app3StderrLog
  try {
    Invoke-WebviewAssertions -App $app3 -Phase "invalid" -DebugPort $DebugPort -ExpectedVersion $RejectedVersion `
      -AppStdoutLog $app3StdoutLog -AppStderrLog $app3StderrLog -AppName $appNameForDiagnostics
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
}
