$ErrorActionPreference = 'Stop'
$script = 'C:\Users\user\wms-training-setup\start-windows.ps1'
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File $script"
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType S4U -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'WMS-387 Training' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Start isolated WMS copy and its WSL HTTP forwarding' -Force | Out-Null
Start-ScheduledTask -TaskName 'WMS-387 Training'
Get-ScheduledTask -TaskName 'WMS-387 Training' | Select-Object TaskName, State
