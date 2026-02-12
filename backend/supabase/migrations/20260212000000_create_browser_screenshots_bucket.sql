BEGIN;

-- Create the browser-screenshots bucket for storing browser tool screenshots
INSERT INTO storage.buckets (id, name, public, allowed_mime_types, file_size_limit)
VALUES (
    'browser-screenshots',
    'browser-screenshots',
    true,
    'image/png,image/jpeg,image/webp,image/gif',
    52428800
)
ON CONFLICT (id) DO UPDATE SET public = EXCLUDED.public;

-- RLS policies for browser-screenshots bucket
DROP POLICY IF EXISTS "Users can upload to browser-screenshots" ON storage.objects;
DROP POLICY IF EXISTS "Browser screenshots are publicly readable" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete their browser screenshots" ON storage.objects;

-- Allow authenticated users to upload screenshots
CREATE POLICY "Users can upload to browser-screenshots" ON storage.objects
FOR INSERT WITH CHECK (
    bucket_id = 'browser-screenshots'
    AND auth.role() = 'authenticated'
);

-- Make screenshots publicly readable (required for LLM access)
CREATE POLICY "Browser screenshots are publicly readable" ON storage.objects
FOR SELECT USING (bucket_id = 'browser-screenshots');

-- Allow users to delete their own screenshots
CREATE POLICY "Users can delete their browser screenshots" ON storage.objects
FOR DELETE USING (
    bucket_id = 'browser-screenshots'
    AND auth.role() = 'authenticated'
);

COMMIT;
