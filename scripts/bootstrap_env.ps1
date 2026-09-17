# bootstrap_env.ps1 - D3.1 / D3.2
# Ensure SECRET_KEY and FIRST_SUPERUSER_PASSWORD in .env are not the insecure
# default "changethis" (or empty). Generate strong random values and persist
# them to .env. The operator reads the (newly generated) password from the
# terminal / .env to log in the first time.
#
# This file is intentionally ASCII-only (English messages). It is executed by
# PowerShell (not cmd.exe), so encoding is not an issue, but keeping it ASCII
# avoids any ambiguity when called from a .cmd via `powershell -File`.
$ErrorActionPreference = 'Stop'

$envFile = Join-Path (Join-Path $PSScriptRoot '..') '.env'
if (-not (Test-Path $envFile)) {
    Write-Error ".env not found (run start.cmd first)"
    exit 1
}

$text = [System.IO.File]::ReadAllText($envFile)
$enc  = [System.Text.UTF8Encoding]::new($false)

function New-RandomString([int]$len) {
    # 0-9 A-Z a-z - _  (URL/env-safe, no characters that break .env parsing)
    $chars = (48..57) + (65..90) + (97..122) + (45, 95)
    -join ($chars | Get-Random -Count $len | ForEach-Object { [char]$_ })
}

function Set-EnvVar([string]$name, [int]$len) {
    $existing = $false
    $cur = $null
    if ($script:text -match "(?m)^$name=(.*)$") {
        $existing = $true
        $cur = $Matches[1].Trim().Trim('"').Trim("'")
    }
    if (-not $existing -or $cur -eq '' -or $cur -eq 'changethis') {
        $v = New-RandomString $len
        if ($existing) {
            $script:text = [regex]::Replace($script:text, "(?m)^$name=.*$", "$name=$v")
        } else {
            $script:text = $script:text.TrimEnd() + "`n$name=$v`n"
        }
        return $v
    }
    return $null
}

$skNew = Set-EnvVar 'SECRET_KEY' 32
$pwNew = Set-EnvVar 'FIRST_SUPERUSER_PASSWORD' 24
[System.IO.File]::WriteAllText($envFile, $text, $enc)

if ($pwNew) {
    Write-Host "IrsBot: a new random admin password was generated and saved to .env."
    Write-Host "       Use it for your first login, then change it in the UI if you like."
}
if ($skNew) {
    Write-Host "IrsBot: a new random SECRET_KEY was generated and saved to .env."
}
