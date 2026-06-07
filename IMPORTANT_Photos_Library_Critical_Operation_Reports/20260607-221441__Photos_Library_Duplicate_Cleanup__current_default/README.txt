Photos Library Duplicate Cleanup Report

run_timestamp: 20260607-221441
library_id: current_default
library_path: /Users/huohsien/Pictures/Photos Library.photoslibrary
inventory_cache_path: /Users/huohsien/workspace/python/explore_photos_library/data/inventory_cache/current_default.inventory.pkl.gz

asset_count: 94683
assets_without_unique_id: 39
duplicate_candidate_group_count: 23
duplicate_candidate_asset_count: 46

status_counts:
{
  "DELETABLE_DUPLICATE": 23
}

safety_counts:
{
  "live_photo_candidate_group_count": 0,
  "location_conflict_group_count": 0,
  "unreadable_original_group_count": 0,
  "sha_error_group_count": 0
}

delete_candidate_asset_count: 23
keep_asset_count: 23
duplicate_review_asset_count: 46
location_conflict_row_count: 0
live_photo_candidate_row_count: 0
assets_without_unique_id_row_count: 39

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
/Users/huohsien/workspace/python/explore_photos_library/IMPORTANT_Photos_Library_Critical_Operation_Reports/20260607-221441__Photos_Library_Duplicate_Cleanup__current_default
