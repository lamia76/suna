# Migration Backup & Verification Script for Suna Backend
# Usage: ./backup_migration.ps1
# Run this BEFORE executing the browser-screenshots bucket migration

param(
    [string]$SupabaseDbUrl = $env:SUPABASE_DB_URL,
    [string]$BackupDir = "./backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')",
    [switch]$SkipDbBackup,
    [switch]$SkipMigrationsBackup,
    [switch]$VerifyOnly = $false
)

# Colors for output
function Write-Success {
    Write-Host "[✓] $args" -ForegroundColor Green
}

function Write-Warning {
    Write-Host "[!] $args" -ForegroundColor Yellow
}

function Write-Error {
    Write-Host "[✗] $args" -ForegroundColor Red
}

function Write-Info {
    Write-Host "[i] $args" -ForegroundColor Cyan
}

# Check prerequisites
Write-Info "Checking prerequisites..."

if (-not (Get-Command pg_dump -ErrorAction SilentlyContinue)) {
    Write-Error "pg_dump not found. Please install PostgreSQL client tools."
    exit 1
}

if (-not $SupabaseDbUrl) {
    Write-Error "SUPABASE_DB_URL environment variable not set."
    Write-Info "Set it with: `$env:SUPABASE_DB_URL='postgresql://...'"
    exit 1
}

Write-Success "Prerequisites OK"

# Create backup directory
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir | Out-Null
    Write-Success "Created backup directory: $BackupDir"
}

# Record current timestamp
$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$backupLog = "$BackupDir/backup_manifest.txt"

# Write backup manifest
@"
Backup Created: $timestamp
Purpose: Pre-migration backup for browser-screenshots bucket migration
Migration File: 20260212000000_create_browser_screenshots_bucket.sql
Rollback File: 20260212000001_rollback_browser_screenshots_bucket.sql

Files in this backup:
"@ | Out-File $backupLog

Write-Info "Starting backup process..."

# 1. Backup database
if (-not $SkipDbBackup) {
    Write-Info "Backing up database..."
    $dbBackupFile = "$BackupDir/database_backup_$($timestamp -replace ':', '-').sql"
    
    try {
        pg_dump $SupabaseDbUrl -f $dbBackupFile -v
        $fileSize = (Get-Item $dbBackupFile).Length / 1MB
        Write-Success "Database backup created: $dbBackupFile ($([math]::Round($fileSize, 2)) MB)"
        "- database_backup_*.sql (Database complete backup)" | Add-Content $backupLog
    }
    catch {
        Write-Error "Database backup failed: $_"
        exit 1
    }
}

# 2. Backup current bucket state
Write-Info "Backing up current bucket state..."
$bucketsFile = "$BackupDir/buckets_state_before.txt"

try {
    $bucketsList = psql $SupabaseDbUrl -c "SELECT id, name, public, created_at FROM storage.buckets ORDER BY created_at DESC;"
    $bucketsList | Out-File $bucketsFile
    Write-Success "Bucket state saved: $bucketsFile"
    "- buckets_state_before.txt (storage.buckets table before migration)" | Add-Content $backupLog
}
catch {
    Write-Warning "Could not backup bucket state: $_"
}

# 3. Backup RLS policies
Write-Info "Backing up RLS policies..."
$policiesFile = "$BackupDir/rls_policies_before.txt"

try {
    $policies = psql $SupabaseDbUrl -c "SELECT schemaname, tablename, policyname, permissive, roles FROM pg_policies WHERE tablename = 'objects' AND schemaname = 'storage';"
    $policies | Out-File $policiesFile
    Write-Success "RLS policies saved: $policiesFile"
    "- rls_policies_before.txt (storage.objects RLS policies before migration)" | Add-Content $backupLog
}
catch {
    Write-Warning "Could not backup RLS policies: $_"
}

# 4. Backup migrations directory
if (-not $SkipMigrationsBackup) {
    Write-Info "Backing up migrations directory..."
    $migrationsBackupDir = "$BackupDir/migrations_backup"
    
    try {
        Copy-Item -Path "./supabase/migrations" -Destination $migrationsBackupDir -Recurse
        $fileCount = (Get-ChildItem $migrationsBackupDir -Recurse).Count
        Write-Success "Migrations directory backed up: $fileCount files"
        "- migrations_backup/ (All migration files)" | Add-Content $backupLog
    }
    catch {
        Write-Warning "Could not backup migrations directory: $_"
    }
}

# 5. Copy migration files for reference
Write-Info "Copying migration files for reference..."

try {
    Copy-Item -Path "./supabase/migrations/20260212000000_create_browser_screenshots_bucket.sql" -Destination "$BackupDir/" -ErrorAction SilentlyContinue
    Copy-Item -Path "./supabase/migrations/20260212000001_rollback_browser_screenshots_bucket.sql" -Destination "$BackupDir/" -ErrorAction SilentlyContinue
    Write-Success "Migration files copied to backup directory"
    "- 20260212000000_create_browser_screenshots_bucket.sql (Forward migration)" | Add-Content $backupLog
    "- 20260212000001_rollback_browser_screenshots_bucket.sql (Rollback migration)" | Add-Content $backupLog
}
catch {
    Write-Warning "Could not copy migration files: $_"
}

# Verification section
Write-Info ""
Write-Info "Verification checks..."

# Check if browser-screenshots bucket already exists
Write-Info "Checking if browser-screenshots bucket already exists..."
try {
    $existing = psql $SupabaseDbUrl -t -c "SELECT id FROM storage.buckets WHERE id='browser-screenshots';"
    if ($existing.Trim()) {
        Write-Warning "browser-screenshots bucket already exists!"
        Write-Info "Migration will use ON CONFLICT to update existing bucket"
    }
    else {
        Write-Success "browser-screenshots bucket does not exist (ready for creation)"
    }
}
catch {
    Write-Warning "Could not verify existing bucket: $_"
}

# Write final summary
@"

Backup Summary:
- Location: $BackupDir
- Timestamp: $timestamp
- Database backed up: $(-not $SkipDbBackup)
- Migrations backed up: $(-not $SkipMigrationsBackup)

Next steps:
1. Review this manifest: $backupLog
2. Execute migration: psql `$SUPABASE_DB_URL -f supabase/migrations/20260212000000_create_browser_screenshots_bucket.sql
3. Verify migration: psql `$SUPABASE_DB_URL -c \"SELECT id, name FROM storage.buckets WHERE id='browser-screenshots';\"
4. If needed, rollback: psql `$SUPABASE_DB_URL -f supabase/migrations/20260212000001_rollback_browser_screenshots_bucket.sql
5. Or restore from backup: psql `$SUPABASE_DB_URL -f $dbBackupFile

IMPORTANT: Keep this backup directory safe until migration is verified in production!

"@ | Add-Content $backupLog

Write-Success ""
Write-Success "Backup completed successfully!"
Write-Info "Backup location: $(Resolve-Path $BackupDir)"
Write-Info ""
Write-Info "Backup manifest:"
Get-Content $backupLog | ForEach-Object { Write-Info $_ }

# Optional: Open backup directory in explorer
if ($PSVersionTable.PSVersion.Major -ge 5) {
    Write-Info ""
    $openBackup = Read-Host "Open backup directory in explorer? (y/n)"
    if ($openBackup -eq 'y') {
        Invoke-Item (Resolve-Path $BackupDir)
    }
}

exit 0
