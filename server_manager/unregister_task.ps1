$ErrorActionPreference = "SilentlyContinue"
Unregister-ScheduledTask -TaskName 'MetalSortingSCADA_AutoServer' -Confirm:$false
Write-Host "Task 'MetalSortingSCADA_AutoServer' unregistered."
