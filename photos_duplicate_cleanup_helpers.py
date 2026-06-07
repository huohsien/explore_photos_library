# photos_duplicate_cleanup_helpers.py
# Helper functions for Photos_Library_Duplicate_Cleanup.ipynb

import os
import json
import csv
import hashlib
import time
from collections import defaultdict, Counter
from datetime import datetime
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")


def parse_datetime_value(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def to_taipei_datetime(value):
    dt = parse_datetime_value(value)
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TAIPEI)
    return dt.astimezone(TAIPEI)


def format_no_year_taipei_datetime(value):
    dt = to_taipei_datetime(value)
    if dt is None:
        return None
    return (
        f"{dt.month:02d}-"
        f"{dt.day:02d} "
        f"{dt.hour:02d}:"
        f"{dt.minute:02d}:"
        f"{dt.second:02d}."
        f"{dt.microsecond:06d}"
    )


def get_file_size_bytes(asset):
    path = asset.get("path")
    if path is None:
        return None
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def normalize_text(value):
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    return text


def normalize_string_tuple(values):
    if not values:
        return tuple()

    normalized = []
    for value in values:
        text = normalize_text(value)
        if text is not None:
            normalized.append(text)

    return tuple(sorted(set(normalized)))


def asset_album_titles(asset):
    albums = asset.get("albums") or {}
    titles = []

    for album in albums.values():
        title = album.get("title")
        if title:
            titles.append(title)

    return normalize_string_tuple(titles)


def asset_folder_paths(asset):
    folders = asset.get("folders") or {}
    paths = []

    for folder in folders.values():
        path = folder.get("path") or folder.get("title")
        if path:
            paths.append(path)

    return normalize_string_tuple(paths)


def make_photo_library_asset_base_id(asset):
    original_filename = asset.get("original_filename")
    no_year_datetime = format_no_year_taipei_datetime(asset.get("date"))
    file_size_bytes = asset.get("file_size_bytes")

    if original_filename is None:
        return None
    if no_year_datetime is None:
        return None
    if file_size_bytes is None:
        return None

    return (
        original_filename,
        no_year_datetime,
        file_size_bytes,
    )


def make_canonical_ourmetadata(asset):
    return (
        ("description", normalize_text(asset.get("description"))),
        ("keywords", normalize_string_tuple(asset.get("keywords") or tuple())),
        ("favorite", bool(asset.get("favorite"))),
        ("hidden", bool(asset.get("hidden"))),
        ("album_titles", asset_album_titles(asset)),
        ("folder_paths", asset_folder_paths(asset)),
    )


def make_photo_library_asset_unique_id(asset):
    base_id = asset.get("photo_library_asset_base_id")
    if base_id is None:
        return None
    return (
        base_id,
        make_canonical_ourmetadata(asset),
    )


def fill_duplicate_cleanup_identity_fields(inventory):
    reason_counter = Counter()

    for asset in inventory["assets"]:
        asset["file_size_bytes"] = get_file_size_bytes(asset)

        base_id = make_photo_library_asset_base_id(asset)
        asset["photo_library_asset_base_id"] = base_id

        if base_id is None:
            if asset.get("original_filename") is None:
                reason_counter["missing original_filename"] += 1
            elif format_no_year_taipei_datetime(asset.get("date")) is None:
                reason_counter["missing/invalid date"] += 1
            elif asset.get("file_size_bytes") is None:
                reason_counter["missing file_size_bytes"] += 1
            else:
                reason_counter["unknown base_id failure"] += 1

            asset["photo_library_asset_unique_id"] = None
            continue

        asset["photo_library_asset_unique_id"] = make_photo_library_asset_unique_id(asset)

    base_id_count = sum(
        1
        for asset in inventory["assets"]
        if asset.get("photo_library_asset_base_id") is not None
    )

    unique_id_count = sum(
        1
        for asset in inventory["assets"]
        if asset.get("photo_library_asset_unique_id") is not None
    )

    print("Filled identity fields")
    print("asset count:", len(inventory["assets"]))
    print("base_id filled:", base_id_count)
    print("unique_id filled:", unique_id_count)

    if reason_counter:
        print()
        print("base_id failure reasons:")
        for reason, count in reason_counter.most_common():
            print(f"- {reason}: {count}")

    print()
    print("First 3 assets after fill:")
    for asset in inventory["assets"][:3]:
        print("-" * 80)
        print("original_filename:", asset.get("original_filename"))
        print("date:", asset.get("date"))
        print("path:", asset.get("path"))
        print("file_size_bytes:", asset.get("file_size_bytes"))
        print("base_id:", asset.get("photo_library_asset_base_id"))
        print("unique_id:", asset.get("photo_library_asset_unique_id"))


def group_assets_by_field(inventory, field_name):
    groups = defaultdict(list)
    missing = []

    for asset in inventory["assets"]:
        value = asset.get(field_name)

        if value is None:
            missing.append(asset)
            continue

        groups[value].append(asset)

    return dict(groups), missing


def sha256_file(path, chunk_size=1024 * 1024):
    sha256 = hashlib.sha256()

    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha256.update(chunk)

    return sha256.hexdigest()


def calculate_asset_sha256(asset):
    path = asset.get("path")

    if path is None:
        return None, "PATH_NONE"

    if not os.path.exists(path):
        return None, "PATH_DOES_NOT_EXIST"

    try:
        sha256 = sha256_file(path)
    except Exception as error:
        return None, f"SHA_ERROR: {error}"

    asset["content_sha256"] = sha256
    return sha256, None


def asset_has_readable_original(asset):
    path = asset.get("path")
    return path is not None and os.path.exists(path)


def get_first_present(asset, field_names):
    for field_name in field_names:
        if field_name in asset and asset.get(field_name) not in (None, "", tuple(), []):
            return asset.get(field_name)
    return None


def asset_live_photo_marker(asset):
    return get_first_present(
        asset,
        [
            "path_live_photo",
            "live_photo_path",
            "live_photo_video_path",
            "live_photo",
            "is_live_photo",
            "isphoto_live",
        ],
    )


def asset_is_live_photo_candidate(asset):
    marker = asset_live_photo_marker(asset)
    if marker is None:
        return False
    if marker is False:
        return False
    return True


def asset_location_value(asset):
    location = get_first_present(
        asset,
        [
            "location",
            "place",
            "gps",
            "latitude_longitude",
        ],
    )

    if location is not None:
        return repr(location)

    lat = get_first_present(asset, ["latitude", "lat"])
    lon = get_first_present(asset, ["longitude", "lon", "lng"])

    if lat is not None or lon is not None:
        return f"{lat},{lon}"

    return None


def stable_sort_assets_for_keep(group):
    def sort_key(asset):
        has_location = asset_location_value(asset) is not None
        date_added = asset.get("date_added") or ""
        path = asset.get("path") or ""
        return (
            0 if has_location else 1,
            date_added,
            path,
        )

    return sorted(group, key=sort_key)


def summarize_asset_for_report(asset):
    return {
        "uuid": asset.get("uuid"),
        "original_filename": asset.get("original_filename"),
        "filename": asset.get("filename"),
        "date": asset.get("date"),
        "date_added": asset.get("date_added"),
        "path": asset.get("path"),
        "asset_scope": asset.get("asset_scope"),
        "file_size_bytes": asset.get("file_size_bytes"),
        "content_sha256": asset.get("content_sha256"),
        "description": asset.get("description"),
        "keywords": list(asset.get("keywords") or []),
        "favorite": asset.get("favorite"),
        "hidden": asset.get("hidden"),
        "album_titles": list(asset_album_titles(asset)),
        "folder_paths": list(asset_folder_paths(asset)),
        "location": asset_location_value(asset),
        "live_photo_marker": repr(asset_live_photo_marker(asset)),
    }


def analyze_duplicate_candidate_groups(duplicate_candidate_groups):
    analysis = []
    total_groups = len(duplicate_candidate_groups)
    t0 = time.perf_counter()

    for index, (unique_id, group) in enumerate(duplicate_candidate_groups.items(), start=1):
        if index % 10 == 0 or index == 1 or index == total_groups:
            print(f"Analyzing group {index}/{total_groups}")

        group_record = {
            "unique_id_repr": repr(unique_id),
            "asset_count": len(group),
            "status": None,
            "reason": None,
            "sha_groups": {},
            "keep_assets": [],
            "delete_candidates": [],
            "assets": [],
        }

        if any(asset_is_live_photo_candidate(asset) for asset in group):
            group_record["status"] = "REPORT_ONLY"
            group_record["reason"] = "LIVE_PHOTO_CANDIDATE_V1_SKIP_AUTO_DELETE"
            group_record["assets"] = [summarize_asset_for_report(asset) for asset in group]
            analysis.append(group_record)
            continue

        unreadable_assets = [
            asset
            for asset in group
            if not asset_has_readable_original(asset)
        ]

        if unreadable_assets:
            group_record["status"] = "REPORT_ONLY"
            group_record["reason"] = "UNREADABLE_ORIGINAL"
            group_record["assets"] = [summarize_asset_for_report(asset) for asset in group]
            analysis.append(group_record)
            continue

        sha_to_assets = defaultdict(list)
        sha_errors = []

        for asset in group:
            sha256, error = calculate_asset_sha256(asset)

            if error is not None:
                sha_errors.append(
                    {
                        "asset": summarize_asset_for_report(asset),
                        "error": error,
                    }
                )
                continue

            sha_to_assets[sha256].append(asset)

        if sha_errors:
            group_record["status"] = "REPORT_ONLY"
            group_record["reason"] = "SHA_ERROR"
            group_record["sha_errors"] = sha_errors
            group_record["assets"] = [summarize_asset_for_report(asset) for asset in group]
            analysis.append(group_record)
            continue

        for sha256, sha_group in sha_to_assets.items():
            group_record["sha_groups"][sha256] = [
                summarize_asset_for_report(asset)
                for asset in sha_group
            ]

        deletable_sha_groups = {
            sha256: sha_group
            for sha256, sha_group in sha_to_assets.items()
            if len(sha_group) > 1
        }

        if not deletable_sha_groups:
            group_record["status"] = "NOT_DUPLICATE"
            group_record["reason"] = "UNIQUE_ID_COLLISION_BUT_SHA_DIFFERS"
            group_record["assets"] = [summarize_asset_for_report(asset) for asset in group]
            analysis.append(group_record)
            continue

        group_record["status"] = "DELETABLE_DUPLICATE"
        group_record["reason"] = "SAME_UNIQUE_ID_AND_SAME_SHA256"

        delete_candidates = []
        keep_assets = []

        for sha256, sha_group in deletable_sha_groups.items():
            sorted_group = stable_sort_assets_for_keep(sha_group)
            keep_asset = sorted_group[0]
            delete_assets = sorted_group[1:]

            keep_assets.append(keep_asset)
            delete_candidates.extend(delete_assets)

        group_record["keep_assets"] = [summarize_asset_for_report(asset) for asset in keep_assets]
        group_record["delete_candidates"] = [summarize_asset_for_report(asset) for asset in delete_candidates]
        group_record["assets"] = [summarize_asset_for_report(asset) for asset in group]

        analysis.append(group_record)

    elapsed = time.perf_counter() - t0
    print("analysis group count:", len(analysis))
    print("elapsed seconds:", round(elapsed, 3))

    return analysis


def count_records_by_status(records):
    counts = defaultdict(int)
    for record in records:
        counts[record.get("status")] += 1
    return dict(sorted(counts.items()))


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_tsv(path, rows, fieldnames):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            delimiter="\t",
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def flatten_delete_candidate_rows(records):
    rows = []

    for group_index, record in enumerate(records, start=1):
        for asset in record.get("delete_candidates") or []:
            rows.append({
                "group_index": group_index,
                "status": record.get("status"),
                "reason": record.get("reason"),
                "uuid": asset.get("uuid"),
                "original_filename": asset.get("original_filename"),
                "filename": asset.get("filename"),
                "date": asset.get("date"),
                "date_added": asset.get("date_added"),
                "path": asset.get("path"),
                "asset_scope": asset.get("asset_scope"),
                "file_size_bytes": asset.get("file_size_bytes"),
                "content_sha256": asset.get("content_sha256"),
                "location": asset.get("location"),
                "album_titles": " | ".join(asset.get("album_titles") or []),
                "folder_paths": " | ".join(asset.get("folder_paths") or []),
                "keywords": " | ".join(asset.get("keywords") or []),
                "favorite": asset.get("favorite"),
                "hidden": asset.get("hidden"),
                "description": asset.get("description"),
            })

    return rows


def flatten_keep_asset_rows(records):
    rows = []

    for group_index, record in enumerate(records, start=1):
        for asset in record.get("keep_assets") or []:
            rows.append({
                "group_index": group_index,
                "status": record.get("status"),
                "reason": record.get("reason"),
                "uuid": asset.get("uuid"),
                "original_filename": asset.get("original_filename"),
                "filename": asset.get("filename"),
                "date": asset.get("date"),
                "date_added": asset.get("date_added"),
                "path": asset.get("path"),
                "asset_scope": asset.get("asset_scope"),
                "file_size_bytes": asset.get("file_size_bytes"),
                "content_sha256": asset.get("content_sha256"),
                "location": asset.get("location"),
                "album_titles": " | ".join(asset.get("album_titles") or []),
                "folder_paths": " | ".join(asset.get("folder_paths") or []),
                "keywords": " | ".join(asset.get("keywords") or []),
                "favorite": asset.get("favorite"),
                "hidden": asset.get("hidden"),
                "description": asset.get("description"),
            })

    return rows


def flatten_location_conflict_rows(records):
    rows = []

    for group_index, record in enumerate(records, start=1):
        assets = record.get("assets") or []

        locations = sorted(set(
            asset.get("location")
            for asset in assets
            if asset.get("location")
        ))

        if len(locations) <= 1:
            continue

        for asset in assets:
            rows.append({
                "group_index": group_index,
                "status": record.get("status"),
                "reason": "LOCATION_VALUES_DIFFER_WITHIN_DUPLICATE_GROUP",
                "uuid": asset.get("uuid"),
                "original_filename": asset.get("original_filename"),
                "date": asset.get("date"),
                "date_added": asset.get("date_added"),
                "path": asset.get("path"),
                "content_sha256": asset.get("content_sha256"),
                "location": asset.get("location"),
            })

    return rows


def write_operation_report(
    report_dir,
    duplicate_analysis,
    inventory,
    assets_without_unique_id,
    duplicate_candidate_groups,
    run_timestamp,
    library_id,
    library_path,
    inventory_cache_path,
):
    delete_candidate_rows = flatten_delete_candidate_rows(duplicate_analysis)
    keep_asset_rows = flatten_keep_asset_rows(duplicate_analysis)
    location_conflict_rows = flatten_location_conflict_rows(duplicate_analysis)
    status_counts = count_records_by_status(duplicate_analysis)

    write_json(report_dir / "duplicate_analysis.json", duplicate_analysis)
    write_json(report_dir / "kept_assets.json", keep_asset_rows)
    write_json(report_dir / "delete_candidates.json", delete_candidate_rows)

    common_tsv_fields = [
        "group_index",
        "status",
        "reason",
        "uuid",
        "original_filename",
        "filename",
        "date",
        "date_added",
        "path",
        "asset_scope",
        "file_size_bytes",
        "content_sha256",
        "location",
        "album_titles",
        "folder_paths",
        "keywords",
        "favorite",
        "hidden",
        "description",
    ]

    write_tsv(report_dir / "delete_candidates.tsv", delete_candidate_rows, common_tsv_fields)
    write_tsv(report_dir / "kept_assets.tsv", keep_asset_rows, common_tsv_fields)

    write_tsv(
        report_dir / "location_conflicts.tsv",
        location_conflict_rows,
        [
            "group_index",
            "status",
            "reason",
            "uuid",
            "original_filename",
            "date",
            "date_added",
            "path",
            "content_sha256",
            "location",
        ],
    )

    summary_text = f"""Photos Library Duplicate Cleanup Report

run_timestamp: {run_timestamp}
library_id: {library_id}
library_path: {library_path}
inventory_cache_path: {inventory_cache_path}

asset_count: {len(inventory["assets"])}
assets_without_unique_id: {len(assets_without_unique_id)}
duplicate_candidate_group_count: {len(duplicate_candidate_groups)}
duplicate_candidate_asset_count: {sum(len(group) for group in duplicate_candidate_groups.values())}

status_counts:
{json.dumps(status_counts, ensure_ascii=False, indent=2)}

delete_candidate_asset_count: {len(delete_candidate_rows)}
keep_asset_count: {len(keep_asset_rows)}
location_conflict_row_count: {len(location_conflict_rows)}

IMPORTANT:
This report folder should be copied/backed up to Google Drive:
{report_dir}
"""

    with open(report_dir / "execution_summary.txt", "w", encoding="utf-8") as f:
        f.write(summary_text)

    with open(report_dir / "README.txt", "w", encoding="utf-8") as f:
        f.write(summary_text)

    print(summary_text)
    print("Report files:")
    for path in sorted(report_dir.iterdir()):
        print(" ", path)

    return {
        "delete_candidate_rows": delete_candidate_rows,
        "keep_asset_rows": keep_asset_rows,
        "location_conflict_rows": location_conflict_rows,
        "status_counts": status_counts,
    }
