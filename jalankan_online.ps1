# Menyalakan SKAKMAT dan membukanya lewat alamat https sementara dari Cloudflare (Quick Tunnel, gratis,
# tanpa akun). Semua teman cukup membuka alamat yang tercetak; tidak ada yang perlu dipasang di perangkat mereka.
#   powershell -ExecutionPolicy Bypass -File .\jalankan_online.ps1
# Tekan Ctrl+C untuk berhenti; server dan terowongan ikut mati.
param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$cf = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cf) {   # PATH sesi ini belum diperbarui setelah pemasangan: cari di lokasi pemasangan umum
    $kandidat = @("${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe", "$env:ProgramFiles\cloudflared\cloudflared.exe",
                  "$env:LOCALAPPDATA\Microsoft\WinGet\Links\cloudflared.exe")
    $cf = $kandidat | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $cf) {
    Write-Host "cloudflared belum terpasang. Pasang sekali dengan:  winget install --id Cloudflare.cloudflared" -ForegroundColor Yellow
    exit 1
}

function Sandi-Acak { -join ((48..57) + (65..90) + (97..122) | Where-Object { $_ -notin 73, 79, 108 } | Get-Random -Count 10 | ForEach-Object { [char]$_ }) }
$s1 = Sandi-Acak; $s2 = Sandi-Acak; $s3 = Sandi-Acak

$db = Join-Path $PSScriptRoot "skakmat_online.db"
Remove-Item $db -ErrorAction SilentlyContinue
$env:SKAKMAT_DB = $db
$env:SKAKMAT_COOKIE_SECURE = "1"
$env:SKAKMAT_SANDI_ANGGOTA1 = $s1
$env:SKAKMAT_SANDI_ANGGOTA2 = $s2
$env:SKAKMAT_SANDI_ANGGOTA3 = $s3

$logTunnel = Join-Path $env:TEMP "skakmat_tunnel.log"
Remove-Item $logTunnel -ErrorAction SilentlyContinue
$server = Start-Process $py -ArgumentList "app.py", "--port", $Port -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 3
$tunnel = Start-Process $cf -ArgumentList "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:$Port" `
    -RedirectStandardError $logTunnel -PassThru -WindowStyle Hidden
try {
    $url = $null
    for ($i = 0; $i -lt 40 -and -not $url; $i++) {
        Start-Sleep -Milliseconds 750
        if (Test-Path $logTunnel) {
            $m = Select-String -Path $logTunnel -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
            if ($m) { $url = $m.Matches[0].Value }
        }
    }
    if (-not $url) { throw "Alamat terowongan tidak muncul. Lihat $logTunnel" }
    Write-Host ""
    Write-Host "SKAKMAT online. Bagikan alamat ini ke teman (satu alamat untuk semua):" -ForegroundColor Green
    Write-Host "  $url" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Akun demo (atau teman bisa Daftar akun baru di halaman masuk). Satu orang satu akun, boleh beda browser/perangkat:"
    Write-Host "  anggota1          kata sandi: $s1"
    Write-Host "  anggota2          kata sandi: $s2"
    Write-Host "  anggota3          kata sandi: $s3"
    Write-Host ""
    Write-Host "Alamat berubah tiap skrip dijalankan dan mati saat skrip dihentikan. Ctrl+C untuk berhenti."
    while ($true) { Start-Sleep -Seconds 5; if ($server.HasExited -or $tunnel.HasExited) { break } }
}
finally {
    foreach ($p in @($tunnel, $server)) { if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }
    Remove-Item $db -ErrorAction SilentlyContinue
    Write-Host "Berhenti."
}
