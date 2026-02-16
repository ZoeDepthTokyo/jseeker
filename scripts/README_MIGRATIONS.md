# jSeeker Migration Scripts

## Output Folder Migration (`migrate_output_folders.py`)

### Purpose
Fixes old resume files stored in the "Not_specified" folder by moving them to proper company-named folders and updating database paths.

### Background
Before v0.3.6, when the LLM couldn't extract a company name, it would return "Not specified" which got sanitized to "Not_specified" for folder names. The fallback chain now extracts company names from URLs, but old files remain in the wrong folder.

### What it does
1. Finds all resumes with files in `output/Not_specified/`
2. Looks up correct company name from database
3. Moves PDF and DOCX files to `output/{Company_Name}/`
4. Updates database `pdf_path` and `docx_path` fields
5. Removes empty "Not_specified" folder

### Usage
```bash
# Preview changes (recommended first)
python scripts/migrate_output_folders.py --dry-run

# Execute migration
python scripts/migrate_output_folders.py
```

### Example Output
```
INFO: Found 6 resumes to migrate
INFO: Resume 18: Migrating to Santander/
INFO:   ✓ Moved PDF: Fede_Ponce_Design_Strategist__Customer_Ex_Not_specified_v1.pdf -> Santander/
INFO:   ✓ Moved DOCX: Fede_Ponce_Design_Strategist__Customer_Ex_Not_specified_v1.docx -> Santander/
INFO:   ✓ Updated database paths
INFO: Migration complete: 6 resumes migrated, 0 errors
```

---

## Cache Cleanup (`clean_cache_placeholders.py`)

### Purpose
Removes cached JD parse results that have placeholder company names, forcing re-parsing with the improved URL fallback chain.

### Background
The semantic cache stores LLM parse results to save API calls. Old cached entries contain placeholder company names ("Not specified", empty string, etc.) from before the URL fallback fix. These cached entries prevent the improved extraction from running.

### What it does
1. Scans file-based cache (`data/.cache/*.json`)
2. Scans database cache (`jd_cache` table)
3. Identifies entries with placeholder companies:
   - "not specified"
   - "unknown"
   - "n/a"
   - "" (empty)
   - etc.
4. Removes these entries so next parse uses URL fallback

### Usage
```bash
# Preview deletions (recommended first)
python scripts/clean_cache_placeholders.py --dry-run

# Execute cleanup
python scripts/clean_cache_placeholders.py
```

### Example Output
```
INFO: Scanning 191 cache files...
INFO: ✓ Removed: 07f1d5e5...json (company: 'Not specified')
INFO: ✓ Removed: 1f5ef3e7...json (company: 'Not specified')
...
INFO: Scanning database cache...
INFO: ✓ Removed DB cache entry #12 (company: 'Not specified')
INFO: Cache cleanup complete: 62 file cache + 3 DB cache = 65 total
```

---

## Recommended Workflow

1. **Run cache cleanup first** (prevents re-creating bad cache)
   ```bash
   python scripts/clean_cache_placeholders.py
   ```

2. **Run folder migration** (fixes existing files)
   ```bash
   python scripts/migrate_output_folders.py
   ```

3. **Verify** - Check that:
   - `output/Not_specified/` is gone or empty
   - Resume files are in correct company folders
   - Database paths point to new locations

## Safety

- Both scripts support `--dry-run` mode
- No data loss - only moves files and updates paths
- Database updates are in transactions (rollback on error)
- Original folder structure preserved if migration fails

## Related Fixes

- **v0.3.6 Task #1**: JD parser now extracts company from URL when LLM fails
- **v0.3.6 Task #4**: These migration scripts + verified fallback chain works
