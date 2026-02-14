BEGIN;

-- Rollback: Drop RLS policies for browser-screenshots bucket
DROP POLICY IF EXISTS "Users can upload to browser-screenshots" ON storage.objects;
DROP POLICY IF EXISTS "Browser screenshots are publicly readable" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete their browser screenshots" ON storage.objects;

-- Rollback: Delete browser-screenshots bucket from storage.buckets table
-- Safe to execute even if bucket doesn't exist or contains objects
-- (objects will remain in storage.objects table but be inaccessible)
DELETE FROM storage.buckets 
WHERE id = 'browser-screenshots';

COMMIT;
