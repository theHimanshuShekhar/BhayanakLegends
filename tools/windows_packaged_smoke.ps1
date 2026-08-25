[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$InstallerPath,
  [Parameter(Mandatory = $true)][string]$InstallRoot,
  [Parameter(Mandatory = $true)][string]$DebugPort,
  [Parameter(Mandatory = $true)][string]$StatePath
)

$ErrorActionPreference = "Stop"
$state = [ordered]@{
  installer = $InstallerPath
  install_root = $InstallRoot
  debug_port = [int]$DebugPort
  phases = @()
  owned_sidecars = @()
  errors = @()
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

  $installSnapshot = @(
    Get-ChildItem -Path $InstallRoot -File -Recurse |
      ForEach-Object { "$($_.FullName)|$((Get-FileHash $_.FullName).Hash)" } |
      Sort-Object
  )

  $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$DebugPort"
  $app = Start-Process -FilePath $appPath -WorkingDirectory (Split-Path $appPath) -PassThru
  try {
    & node tools/windows_packaged_smoke.mjs --phase valid --debug-port $DebugPort
    if ($LASTEXITCODE -ne 0) { throw "webview assertion failed during activation phase" }
    $state.phases += [ordered]@{ name = "activated"; result = "passed" }
  } catch {
    $state.phases += [ordered]@{ name = "activated"; result = "failed"; error = $_.Exception.Message }
    throw
  } finally {
    Close-App -App $app -BaselineSidecars $baseline
  }
  Save-State

  if ($env:FIXTURE_PID) {
    Stop-Process -Id ([int]$env:FIXTURE_PID) -Force -ErrorAction SilentlyContinue
  }
  Remove-Item Env:BHAYANAK_PACK_RELEASE_MANIFEST_URL -ErrorAction SilentlyContinue

  $app = Start-Process -FilePath $appPath -WorkingDirectory (Split-Path $appPath) -PassThru
  try {
    & node tools/windows_packaged_smoke.mjs --phase durable --debug-port $DebugPort
    if ($LASTEXITCODE -ne 0) { throw "webview assertion failed during durable restart phase" }
    $state.phases += [ordered]@{ name = "durable"; result = "passed" }
  } catch {
    $state.phases += [ordered]@{ name = "durable"; result = "failed"; error = $_.Exception.Message }
    throw
  } finally {
    Close-App -App $app -BaselineSidecars $baseline
  }
  Save-State
  $installAfter = @(
    Get-ChildItem -Path $InstallRoot -File -Recurse |
      ForEach-Object { "$($_.FullName)|$((Get-FileHash $_.FullName).Hash)" } |
      Sort-Object
  )
  $installChanges = Compare-Object -ReferenceObject $installSnapshot -DifferenceObject $installAfter
  if ($installChanges) {
    $state.errors += "installed files changed during pack activation/restart"
    throw "packaged install files were modified at runtime"
  }
  $state.install_files_unchanged = $true
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
