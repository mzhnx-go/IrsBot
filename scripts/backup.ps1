# backup.ps1 - IrsBot one-shot, read-only backup (NEVER deletes data)
# Backs up: container app DB, local app DB, .env, raw KB/upload files, irsbot docker volumes.
$ErrorActionPreference = 'Stop'

$proj = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

# --- read .env for credentials ---
$envPath = Join-Path $proj '.env'
$map = @{}
if (Test-Path $envPath) {
    foreach ($line in [System.IO.File]::ReadAllLines($envPath)) {
        $s = $line.Trim()
        if ($s -eq '' -or $s.StartsWith('#')) { continue }
        if ($s -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            $k = $Matches[1]
            $v = $Matches[2].Trim().Trim('"').Trim("'")
            $map[$k] = $v
        }
    }
}
$pgUser = if ($map.ContainsKey('POSTGRES_USER')) { $map['POSTGRES_USER'] } else { 'postgres' }
$pgPw   = if ($map.ContainsKey('POSTGRES_PASSWORD')) { $map['POSTGRES_PASSWORD'] } else { '' }
$pgDb   = if ($map.ContainsKey('POSTGRES_DB')) { $map['POSTGRES_DB'] } else { 'app' }

$ts  = (Get-Date).ToString('yyyyMMdd_HHmmss')
$bak = Join-Path $proj ('backups\' + $ts)
New-Item -ItemType Directory -Path $bak | Out-Null
$bakFS = $bak -replace '\\', '/'
$manifest = Join-Path $bak 'MANIFEST.txt'
function M($s){ $s | Out-File -Append -Encoding utf8 $manifest }

M ("IrsBot backup @ " + $ts)
M ("project : " + $proj)
M ("pg      : user=$pgUser db=$pgDb")
M ''

# 1) container app DB (authoritative live data)
$container = 'irsbot-db-1'
$tmpDump = ('/tmp/irsbot_app_' + $ts + '.dump')
$outC = Join-Path $bak ('irsbot_app_container_' + $ts + '.dump')
Write-Host ("[1/6] Dumping container DB via " + $container + " ...")
docker exec -e ("PGPASSWORD=" + $pgPw) $container pg_dump -U $pgUser -d $pgDb -Fc -f $tmpDump 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "container pg_dump failed (exit $LASTEXITCODE)" }
docker cp ($container + ':' + $tmpDump) $outC 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "docker cp failed (exit $LASTEXITCODE)" }
docker exec $container rm -f $tmpDump 2>&1 | Out-Null
$csize = (Get-Item $outC).Length
M ("container_app_dump : irsbot_app_container_$ts.dump ($csize bytes) [custom fmt; users/provider_configs/conversations; password HASHES present]")

# 2) local app DB (currently empty; captured for completeness)
$outL = Join-Path $bak ('irsbot_app_local_' + $ts + '.dump')
Write-Host '[2/6] Dumping local PostgreSQL app DB ...'
$env:PGPASSWORD = $pgPw
& 'D:\PostgreSQL\bin\pg_dump.exe' -h localhost -p 5432 -U $pgUser -d $pgDb -Fc -f $outL 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    M 'local_app_dump : SKIPPED (pg_dump failed; local DB may be empty/unreachable)'
    Write-Host '  [warn] local pg_dump failed; continuing.'
} else {
    $lsize = (Get-Item $outL).Length
    M ("local_app_dump : irsbot_app_local_$ts.dump ($lsize bytes)")
}

# 3) .env config backup (contains SECRET_KEY, API keys, DB password, admin password)
$envOut = Join-Path $bak ('env_backup_' + $ts + '.env')
Copy-Item $envPath $envOut
M ("env_backup : env_backup_$ts.env  [SECRET: SECRET_KEY + API keys + DB pw + admin pw]")

# 4) raw KB / upload files (knowledge base source documents + attachments)
#    These live under backend/uploads (KB_FILE_STORAGE_DIR). In dev mode the
#    override syncs ./backend into the container, so the host copy is the source
#    of truth. Restoring PG + Milvus without these leaves RAG indexes without
#    their original files -> re-indexing would have nothing to read.
$upSrc = Join-Path $proj 'backend\uploads'
$upDst = Join-Path $bak 'uploads'
Write-Host '[4/6] Copying raw KB / upload files ...'
if (Test-Path $upSrc) {
    if (-not (Test-Path $upDst)) { New-Item -ItemType Directory -Path $upDst | Out-Null }
    # /E copy subdirs, /R:0 no retry on lock, /XJ no junction, /NFL /NDL quiet
    robocopy $upSrc $upDst /E /R:0 /W:0 /NFL /NDL /XJ 2>&1 | Out-Null
    $upCount = (Get-ChildItem $upDst -Recurse -File).Count
    M ("uploads : copied $upCount file(s) -> uploads\  [KB source docs + attachments]")
} else {
    M 'uploads : SKIPPED (backend\uploads not found)'
}

# 5) irsbot docker volumes (Milvus raw data). Tar only if a helper image exists.
Write-Host '[5/6] Backing up irsbot docker volumes ...'
$vols = @(docker volume ls --format '{{.Name}}' | Where-Object { $_ -like 'irsbot*' })
$helper = $null
$imgs = @(docker images --format '{{.Repository}}:{{.Tag}}')
if ($imgs -match 'busybox') { $helper = 'busybox' }
elseif ($imgs -match 'alpine') { $helper = 'alpine' }
if ($vols.Count -eq 0) {
    M 'volumes : none found (irsbot*)'
} elseif (-not $helper) {
    M 'volumes : SKIPPED tar (no busybox/alpine locally). Preserved by "docker compose down" WITHOUT -v.'
    M '          manual: docker run --rm -v <vol>:/v -v <hostdir>:/b busybox tar czf /b/<vol>.tar.gz -C /v .'
} else {
    foreach ($v in $vols) {
        $vf = ($v + '_' + $ts + '.tar.gz')
        docker run --rm -v ($v + ':/volume') -v ($bakFS + ':/backup') $helper tar czf ('/backup/' + $vf) -C /volume . 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { M ("volume : $v -> $vf") }
        else { M ("volume : $v SKIPPED (tar failed)") }
    }
}

# 6) gitignore
Write-Host '[6/6] Ensuring backups/ is git-ignored ...'
$gitig = Join-Path $proj '.gitignore'
$need = $false
if (Test-Path $gitig) { if (-not (Select-String -Quiet -Pattern '^backups/' $gitig)) { $need = $true } } else { $need = $true }
if ($need) { Add-Content -Path $gitig -Value "`n# backup dumps (may contain secrets)`nbackups/" }
M ''
M 'gitignore : backups/ ensured (do NOT commit dumps)'
M 'DONE'

Write-Host ("Backup complete -> " + $bak)
Get-ChildItem $bak | ForEach-Object { Write-Host ("  " + $_.Name + "  (" + $_.Length + " bytes)") }
