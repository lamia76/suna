# Browser Screenshot Upload Fix

## Problem Summary

Browser tool screenshot upload fails with "bucket not found" error when attempting to save screenshots from browser automation.

**Error**: `BucketNotFoundError` when calling `upload_base64_image(screenshot_data, "browser-screenshots")`

**Root Cause**: The `browser-screenshots` Supabase storage bucket is referenced in code but was never created in the database, despite being explicitly allowed in the `file_uploads` table schema constraint.

## Timeline

- **Discovered**: Code in `core/tools/browser_tool.py#L311` calls upload to "browser-screenshots" bucket
- **Schema Check**: `supabase/migrations/20250821093710_agent_file_upload.sql` includes "browser-screenshots" in CHECK constraint but never creates the bucket
- **Impact**: All browser tool screenshot operations fail immediately on upload stage
- **Severity**: HIGH - Core feature (browser automation screenshots) is non-functional

## Affected Files

| File | Issue | Impact |
|------|-------|--------|
| `core/tools/browser_tool.py#L311` | References "browser-screenshots" bucket | Screenshot upload fails |
| `core/utils/s3_upload_utils.py` | Properly designed but bucket doesn't exist | Cannot fulfill upload request |
| `supabase/migrations/20250821093710_agent_file_upload.sql` | Schema allows bucket but doesn't create it | Database inconsistency |
| `supabase/migrations/20260212000000_create_browser_screenshots_bucket.sql` | **NEW** - Creates missing bucket | Fixes the issue |

## Solution

### Implementation Files

Three new files have been created in the repository:

1. **Forward Migration**: `supabase/migrations/20260212000000_create_browser_screenshots_bucket.sql`
   - Creates the `browser-screenshots` storage bucket
   - Configures public access (required for serving images)
   - Sets MIME type restrictions (PNG, JPEG, WebP)
   - Implements Row-Level Security (RLS) policies for authenticated users
   - Safe: Uses transaction isolation and `ON CONFLICT` handling

2. **Reverse Migration**: `supabase/migrations/20260212000001_rollback_browser_screenshots_bucket.sql`
   - Safely removes the bucket (drops RLS policies first)
   - Allows complete rollback if needed
   - Uses `IF EXISTS` for safety (can be run multiple times)

3. **Backup Script**: `backup_migration.ps1`
   - Automated PowerShell script for pre-migration safety
   - Creates timestamped backup directory with:
     - Complete database dump (`pg_dump`)
     - Bucket state snapshot
     - RLS policies documentation
     - Migrations directory backup
   - Includes verification checks and rollback instructions

## Execution Instructions

### Prerequisites

Before executing the migration, ensure:
- PostgreSQL client tools (`psql`, `pg_dump`) are installed
- `$env:SUPABASE_DB_URL` environment variable is set
- Supabase project credentials are accessible
- Backend service can be restarted (Docker or local uvicorn)

### Step 1: Create Backup

```powershell
cd suna/backend
./backup_migration.ps1
```

This creates a timestamped backup directory (e.g., `backup_20260213_143022/`) containing:
- `database_backup_*.sql` - Full database backup
- `buckets_state_before.txt` - Current bucket configuration
- `rls_policies_before.txt` - Current RLS policy definitions
- `migrations_backup/` - Copy of all migration files
- `backup_manifest.txt` - File listing and checksums

**Save the backup directory name for reference in rollback scenarios.**

### Step 2: Execute Forward Migration

Using **psql** (recommended):
```powershell
psql $env:SUPABASE_DB_URL -f supabase/migrations/20260212000000_create_browser_screenshots_bucket.sql
```

Or using **Supabase CLI**:
```bash
supabase migration up --linked
```

Or using **Docker Compose**:
```powershell
docker-compose -f backend/docker-compose.yml exec postgres psql $env:SUPABASE_DB_URL -f migrations/20260212000000_create_browser_screenshots_bucket.sql
```

### Step 3: Verify Success

Run these verification queries:

**Check bucket was created:**
```sql
SELECT id, name, public, file_size_limit, allowed_mime_types 
FROM storage.buckets 
WHERE id = 'browser-screenshots';
```

Expected output:
```
id                    | browser-screenshots
name                  | browser-screenshots
public                | true
file_size_limit       | 52428800
allowed_mime_types    | ["image/png", "image/jpeg", "image/webp"]
```

**Check RLS policies are in place:**
```sql
SELECT schemaname, tablename, policyname, permissive 
FROM pg_policies 
WHERE policyname LIKE '%browser%' OR tablename = 'objects';
```

Expected output (3 policies):
```
browser_screenshots_upload   | INSERT | Allow authenticated users to upload
browser_screenshots_read     | SELECT | Allow public read access
browser_screenshots_delete   | DELETE | Allow authenticated users to delete
```

**Check migration record in schema_migrations:**
```sql
SELECT version, name FROM schema_migrations 
WHERE version = '20260212000000';
```

Expected output:
```
20260212000000 | create_browser_screenshots_bucket
```

### Step 4: Restart Backend Service

**Using Docker Compose:**
```powershell
docker-compose -f backend/docker-compose.yml restart api
```

**Using Local Uvicorn:**
```powershell
# Stop current process and restart
python backend/api.py
```

Wait for service to fully start (check logs for "Application startup complete").

### Step 5: Test Browser Tool

1. Open Suna dashboard/UI
2. Trigger a browser tool execution with screenshot enabled
3. Verify screenshot is captured and uploaded
4. Check backend logs for: `"Successfully uploaded image to storage"`
5. Verify screenshot appears in UI or can be downloaded

## Verification Checklist

- [ ] Backup directory created with all expected files
- [ ] Migration executed without errors
- [ ] `storage.buckets` contains `browser-screenshots` row
- [ ] 3 RLS policies exist (`upload`, `read`, `delete`)
- [ ] Migration version recorded in `schema_migrations`
- [ ] Backend service restarted successfully
- [ ] Browser tool screenshot executes with at least one image capture
- [ ] Image upload succeeds (no bucket errors in logs)
- [ ] Screenshot persists and can be retrieved

## Rollback Procedures

If issues occur, you have three options for rollback:

### Option A: Reverse Migration (Recommended)

Automatically reverts all schema changes:

```powershell
psql $env:SUPABASE_DB_URL -f supabase/migrations/20260212000001_rollback_browser_screenshots_bucket.sql
```

This removes:
- All 3 RLS policies
- The bucket record from `storage.buckets` table

**Safest option**: Idempotent (can run multiple times) and leaves data intact.

### Option B: Restore from Database Backup

If bucket deletion failed or you need full DB restore:

```powershell
# Before restoring, backup current state
pg_dump $env:SUPABASE_DB_URL > database_backup_current.sql

# Restore from backup created in Step 1
psql $env:SUPABASE_DB_URL < backup_YYYYMMDD_HHMMSS/database_backup_*.sql
```

**Suitable for**: Complete rollback including any related changes

### Option C: Manual Cleanup

If neither migration nor restore work:

```sql
-- Drop RLS policies
DROP POLICY IF EXISTS "browser_screenshots_upload" ON storage.objects;
DROP POLICY IF EXISTS "browser_screenshots_read" ON storage.objects;
DROP POLICY IF EXISTS "browser_screenshots_delete" ON storage.objects;

-- Delete bucket record
DELETE FROM storage.buckets WHERE id = 'browser-screenshots';

-- Verify removal
SELECT id FROM storage.buckets WHERE id = 'browser-screenshots';  -- Should return 0 rows
```

## Reversibility Analysis

This fix is completely reversible because:

1. **No data dependencies**: The bucket starts empty, so deletion doesn't lose data
2. **Idempotent migrations**: Both forward and reverse migrations use `IF [NOT] EXISTS` clauses
3. **No schema changes**: Only adds new bucket and policies, doesn't alter existing tables
4. **Full backups**: Automated backup script captures complete database state pre-migration
5. **Multiple rollback paths**: 3 distinct methods to undo changes with varying complexity levels

## Risk Assessment

| Risk Factor | Level | Mitigation |
|------------|-------|-----------|
| Data loss | LOW | Backup before migration captures all state |
| Downtime | LOW | Migration runs in milliseconds, no schema locks |
| Conflicts | LOW | No existing 'browser-screenshots' bucket to collide with |
| Breaking changes | LOW | New RLS policies only apply to new bucket |
| Reproducibility | LOW | Migration is idempotent and versioned |

**Overall**: LOW-RISK change with HIGH-VALUE fix for browser tool functionality

## Migration Files Detail

### Forward Migration (create bucket)

- **File**: `supabase/migrations/20260212000000_create_browser_screenshots_bucket.sql`
- **Size**: ~15 lines
- **Idempotent**: Yes (uses `ON CONFLICT DO NOTHING`)
- **Transactional**: Yes (wrapped in `BEGIN/COMMIT`)
- **RLS Policies**: 3 (upload, read, delete for authenticated users)

### Reverse Migration (drop bucket)

- **File**: `supabase/migrations/20260212000001_rollback_browser_screenshots_bucket.sql`
- **Size**: ~12 lines
- **Idempotent**: Yes (uses `IF EXISTS`)
- **Transactional**: Yes (wrapped in `BEGIN/COMMIT`)
- **Safety**: Drops policies first to avoid constraint violations

### Backup Script

- **File**: `backup_migration.ps1`
- **Language**: PowerShell 5.1+
- **Size**: ~340 lines
- **Features**: Error handling, progress indicators, verification checks
- **Output**: Timestamped directory with database dump and state snapshots

## Troubleshooting

### Bucket Creation Fails: "Key already exists"

**Cause**: Bucket might already exist from incomplete prior attempt

**Fix**:
```sql
-- Check if bucket exists
SELECT id FROM storage.buckets WHERE id = 'browser-screenshots';

-- If it exists, either:
-- Option 1: Drop and recreate
DELETE FROM storage.buckets WHERE id = 'browser-screenshots';

-- Option 2: Just add missing RLS policies
CREATE POLICY "browser_screenshots_upload" ON storage.objects
  FOR INSERT WITH CHECK (bucket_id = 'browser-screenshots' AND auth.role() = 'authenticated_user');
```

### RLS Policy Creation Fails: "Table does not exist"

**Cause**: Storage schema might not be initialized

**Fix**:
```sql
-- Verify storage schema exists
SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'storage';

-- If missing, initialize Supabase storage:
-- Re-run initial Supabase setup or contact Supabase support
```

### Migration Not Recording: Version Not in schema_migrations

**Cause**: psql executed migration but didn't update tracking table

**Fix**:
```sql
-- Manually record migration
INSERT INTO schema_migrations (version, name) 
VALUES ('20260212000000', 'create_browser_screenshots_bucket')
ON CONFLICT DO NOTHING;
```

### Upload Still Fails: "Access Denied" from Supabase

**Cause**: RLS policies too restrictive or incorrect user role

**Verify**:
```sql
-- Check policy definitions
SELECT definition FROM pg_policies 
WHERE tablename = 'objects' AND schemaname = 'storage';

-- Check if user has 'authenticated_user' role
-- Re-run forward migration which includes correct policies
```

## Testing Strategy

### Functional Test

```python
# In suna/backend, test directly:
from core.tools.browser_tool import BrowserTool
from core.utils.s3_upload_utils import upload_base64_image

tool = BrowserTool()
screenshot = tool.screenshot()
result = await upload_base64_image(screenshot, "browser-screenshots")
assert result is not None  # Should return URL or success indicator
```

### Integration Test

1. Trigger browser tool through UI
2. Monitor logs for: `"uploading to bucket: browser-screenshots"`
3. Verify no error: `"BucketNotFoundError"`
4. Check Supabase dashboard: screenshot appears in browser-screenshots bucket
5. Verify file metadata: `public: true`, correct MIME type, timestamp updated

### Regression Test

Ensure other buckets still work:
```sql
-- Test other bucket operations still work
SELECT COUNT(*) FROM storage.objects 
WHERE bucket_id IN ('file-uploads', 'image-uploads', 'agent-profile-images');
```

## Documentation Files

All related documentation is located in:

- **This file**: `suna/BROWSER_SCREENSHOT_FIX.md` (comprehensive overview)
- **Technical guide**: `suna/MIGRATION_BACKUP_ROLLBACK_GUIDE.md` (detailed procedures)
- **Migrations**: `suna/backend/supabase/migrations/2026021200000[0-1]_*` (SQL files)
- **Backup script**: `suna/backend/backup_migration.ps1` (automation)

## Support

For issues:

1. Check **Troubleshooting** section above
2. Review **Rollback Procedures** if migration failed
3. Consult **backup_migration.ps1** output for detailed error messages
4. Reference **MIGRATION_BACKUP_ROLLBACK_GUIDE.md** for extended procedures

## Related Issues

This fix resolves:
- Browser tool screenshot upload failures
- "bucket not found" errors in logs
- Incomplete bucket initialization in original migrations

This does NOT affect:
- File upload tool (uses 'file-uploads' bucket)
- Image upload tool (uses 'image-uploads' bucket)
- Agent profile images (uses 'agent-profile-images' bucket)
- Any other functionality outside browser tool

## Change Summary

| Item | Status | Details |
|------|--------|---------|
| Forward migration | ✅ Created | `20260212000000_create_browser_screenshots_bucket.sql` |
| Reverse migration | ✅ Created | `20260212000001_rollback_browser_screenshots_bucket.sql` |
| Backup script | ✅ Created | `backup_migration.ps1` (340 lines) |
| Technical guide | ✅ Created | `MIGRATION_BACKUP_ROLLBACK_GUIDE.md` (400 lines) |
| Main documentation | ✅ Created | This file (comprehensive overview) |
| Code changes | ✅ None | Issue is in database schema, not application code |
| Breaking changes | ✅ None | Only adds new bucket, fully backward compatible |

---

## Quick Reference

| Task | Command |
|------|---------|
| Create backup | `./backup_migration.ps1` |
| Run migration | `psql $env:SUPABASE_DB_URL -f supabase/migrations/20260212000000_*` |
| Verify bucket | `SELECT id FROM storage.buckets WHERE id='browser-screenshots'` |
| View RLS policies | `SELECT policyname FROM pg_policies WHERE tablename='objects'` |
| Rollback | `psql $env:SUPABASE_DB_URL -f supabase/migrations/20260212000001_*` |
| Restore backup | `psql $env:SUPABASE_DB_URL < backup_*/database_backup_*.sql` |

---

**Last Updated**: February 13, 2026  
**Status**: Ready for production deployment  
**Priority**: HIGH (core browser tool functionality)
