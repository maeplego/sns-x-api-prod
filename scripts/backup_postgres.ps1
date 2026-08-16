# Backup sns_x_prod via pg_dump (Compose host port 5434 by default).
param(
    [string]$OutFile = ("backup_{0:yyyyMMdd_HHmmss}.dump" -f (Get-Date)),
    [string]$HostName = $(if ($env:POSTGRES_HOST) { $env:POSTGRES_HOST } else { "localhost" }),
    [int]$Port = $(if ($env:POSTGRES_PORT) { [int]$env:POSTGRES_PORT } else { 5434 }),
    [string]$User = $(if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "sns" }),
    [string]$Db = $(if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "sns_x_prod" })
)

$env:PGPASSWORD = if ($env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD } else { "sns" }
Write-Host "Dumping $Db @ ${HostName}:${Port} -> $OutFile"
& pg_dump -h $HostName -p $Port -U $User -d $Db -Fc -f $OutFile
Write-Host "Done: $OutFile"
