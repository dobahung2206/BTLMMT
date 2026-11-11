$ErrorActionPreference = "Stop"

$DaemonScript = Join-Path $PSScriptRoot "scada_daemon.py"
$Pythonw = "$env:LOCALAPPDATA\Programs\Python\Python312\pythonw.exe"
if (-not (Test-Path $Pythonw)) {
    $Pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
}

$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$DaemonScript`"" -WorkingDirectory $PSScriptRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Days 0)

$RegisteredTask = Register-ScheduledTask -TaskName 'MetalSortingSCADA_AutoServer' -Action $Action -Trigger $Trigger -Settings $Settings -Force
Write-Host "SUCCESS: Task '$($RegisteredTask.TaskName)' registered with state '$($RegisteredTask.State)'"
