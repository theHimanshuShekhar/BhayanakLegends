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

  $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$DebugPort"
  foreach ($phase in @("valid", "invalid")) {
    $app = Start-Process -FilePath $appPath -WorkingDirectory (Split-Path $appPath) -PassThru
    try {
      & node tools/windows_packaged_smoke.mjs --phase $phase --debug-port $DebugPort
      if ($LASTEXITCODE -ne 0) { throw "webview assertion failed during $phase phase" }
      $state.phases += [ordered]@{ name = $phase; result = "passed" }
    } catch {
      $state.phases += [ordered]@{ name = $phase; result = "failed"; error = $_.Exception.Message }
      throw
    } finally {
      Close-App -App $app -BaselineSidecars $baseline
    }
    Save-State
  }
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
