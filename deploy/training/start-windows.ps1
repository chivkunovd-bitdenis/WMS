$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$env:WSL_UTF8 = '1'
$distribution = 'Ubuntu-24.04'
& wsl -d $distribution -u root --exec /usr/bin/true
if ($LASTEXITCODE -ne 0) { throw 'WSL failed to start' }
$address = ((& wsl -d $distribution -u root --exec hostname -I).Trim() -split '\s+')[0]
if ($address -notmatch '^\d+\.\d+\.\d+\.\d+$') { throw 'WSL IPv4 address unavailable' }
Set-Service iphlpsvc -StartupType Automatic
Start-Service iphlpsvc
# This deployment owns only the previously unused host port 8088.
& netsh interface portproxy delete v4tov4 listenport=8088 listenaddress=0.0.0.0 | Out-Null
& netsh interface portproxy add v4tov4 listenport=8088 listenaddress=0.0.0.0 connectport=8088 connectaddress=$address | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'HTTP port forwarding failed' }
if (-not (Get-NetFirewallRule -DisplayName 'WMS Training HTTP' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName 'WMS Training HTTP' -Direction Inbound -Protocol TCP -LocalPort 8088 -Action Allow | Out-Null
}
& wsl -d $distribution -u root --exec bash -lc 'cd /opt/wms-training && docker compose up -d'
if ($LASTEXITCODE -ne 0) { throw 'Training containers failed to start' }
# WSL systemd services alone do not keep a distribution running.
& wsl -d $distribution -u root --exec sleep infinity
