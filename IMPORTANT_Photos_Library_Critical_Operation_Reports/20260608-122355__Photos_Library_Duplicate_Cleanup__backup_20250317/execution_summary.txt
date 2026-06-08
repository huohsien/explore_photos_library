Photos Library Duplicate Cleanup Report

run_timestamp: 20260608-122355
library_id: backup_20250317
library_path: /Volumes/NEW-PRO-G40--20250315/Photos Library-iCloud-20250317（iCloud 20250325崩潰前最後的備份）--opened by macOS Sequoia on 20260604.photoslibrary
inventory_cache_path: /Users/huohsien/workspace/python/explore_photos_library/data/inventory_cache/backup_20250317.inventory.pkl.gz

asset_count: 71599
assets_without_unique_id: 0
duplicate_candidate_group_count: 21
duplicate_candidate_asset_count: 42

status_counts:
{
  "DELETABLE_DUPLICATE": 21
}

safety_counts:
{
  "live_photo_candidate_group_count": 0,
  "location_conflict_group_count": 0,
  "unreadable_original_group_count": 0,
  "sha_error_group_count": 0
}

delete_candidate_asset_count: 21
keep_asset_count: 21
duplicate_review_asset_count: 42
location_conflict_row_count: 0
live_photo_candidate_row_count: 0
assets_without_unique_id_row_count: 0

Duplicate cleanup v1 decision rule:
- date_added is NOT part of photo_library_asset_unique_id.
- date_added can change after export/import/repair/PowerPhotos copy/iCloud recovery.
- Deletable duplicate requires same photo_library_asset_unique_id and same SHA256.
- Location is NOT part of photo_library_asset_unique_id.
- Keep preference: non-empty GPS/location first, then earliest date_added, then stable path order.
- If multiple non-empty location values conflict inside one candidate group, v1 reports only and does not auto-delete.
- Live Photo candidates are report-only in v1.

IMPORTANT:
This report folder should be copied/backed up to Google Drive:
/Users/huohsien/workspace/python/explore_photos_library/IMPORTANT_Photos_Library_Critical_Operation_Reports/20260608-122355__Photos_Library_Duplicate_Cleanup__backup_20250317
