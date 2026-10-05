param([string]$Helper)
$ErrorActionPreference = 'Stop'
. $Helper
try { Check-Docker | Out-Null } catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }
