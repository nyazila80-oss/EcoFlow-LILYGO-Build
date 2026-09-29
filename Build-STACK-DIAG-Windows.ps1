$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$pio = (Get-Command pio -ErrorAction SilentlyContinue).Source
if (-not $pio) {
  $candidate = Join-Path $env:USERPROFILE '.platformio\penv\Scripts\platformio.exe'
  if (Test-Path $candidate) { $pio = $candidate }
}
if (-not $pio) { throw 'PlatformIO CLI not found. Run in a PlatformIO-enabled VS Code terminal.' }

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logDir = Join-Path $PSScriptRoot ('stack-build-' + $stamp)
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

Write-Host 'Full clean (no upload)'
& $pio run -e lilygo_tcan485_ota -t clean 2>&1 | Tee-Object -FilePath (Join-Path $logDir '01-clean.txt')
if ($LASTEXITCODE -ne 0) { throw "Clean failed; logs: $logDir" }

Write-Host 'Build and link firmware (no upload)'
& $pio run -e lilygo_tcan485_ota 2>&1 | Tee-Object -FilePath (Join-Path $logDir '02-build.txt')
if ($LASTEXITCODE -ne 0) { throw "Build failed; logs: $logDir" }

Write-Host 'Resolved PlatformIO packages'
& $pio pkg list -e lilygo_tcan485_ota 2>&1 | Tee-Object -FilePath (Join-Path $logDir '03-packages.txt')

$buildDir = Join-Path $PSScriptRoot '.pio\build\lilygo_tcan485_ota'
$artifacts = @('firmware.bin', 'firmware.elf', 'firmware.map')
$hashes = foreach ($name in $artifacts) {
  $file = Join-Path $buildDir $name
  if (Test-Path $file) {
    $info = Get-Item $file
    $hash = Get-FileHash -Algorithm SHA256 $file
    [PSCustomObject]@{Name=$name; Bytes=$info.Length; SHA256=$hash.Hash}
  }
}
$hashes | Format-Table -AutoSize | Out-String | Set-Content -Path (Join-Path $logDir '04-artifacts.txt')
Write-Host "Build complete. Logs: $logDir"
Write-Host 'No firmware or filesystem was uploaded.'
