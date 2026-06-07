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
    # Canonical location value for duplicate cleanup safety checks.
    #
    # Location is not part of photo_library_asset_unique_id.
    # It is used only for keep preference and conflict reporting.
    latitude = get_first_present(asset, ["latitude", "lat"])
    longitude = get_first_present(asset, ["longitude", "lon", "lng"])

    if latitude is not None and longitude is not None:
        return f"{latitude},{longitude}"

    location = get_first_present(
        asset,
        [
            "location",
            "gps",
            "latitude_longitude",
        ],
    )

    if location is not None:
        return repr(location)

    return None


def asset_has_location(asset):
    return asset_location_value(asset) is not None


def location_values_for_group(group):
    return sorted(
        set(
            asset_location_value(asset)
            for asset in group
            if asset_location_value(asset) is not None
        )
    )


def group_has_location_conflict(group):
    # v1 safety rule:
    # If multiple non-empty location values exist inside one otherwise
    # deletable duplicate group, do not auto-delete. Report only.
    return len(location_values_for_group(group)) > 1


def keep_sort_key(asset):
    # v1 keep priority:
    # 1. Prefer non-empty GPS/location.
    # 2. Prefer earliest date_added.
    # 3. Prefer stable path order.
    has_location = asset_has_location(asset)
    date_added = asset.get("date_added") or ""
    path = asset.get("path") or ""

    return (
        0 if has_location else 1,
        date_added,
        path,
    )


def stable_sort_assets_for_keep(group):
    return sorted(group, key=keep_sort_key)


def summarize_keep_sort_key(asset):
    return {
        "has_location": asset_has_location(asset),
        "location": asset_location_value(asset),
        "date_added": asset.get("date_added"),
        "path": asset.get("path"),
    }


def summarize_keep_decision_reason(asset, keep_asset):
    if asset.get("uuid") == keep_asset.get("uuid"):
        if asset_has_location(asset):
            return (
                "KEEP: selected by v1 keep rule; candidate has location, "
                "then earliest date_added / stable path order."
            )

        return (
            "KEEP: selected by v1 keep rule; no location advantage found, "
            "then earliest date_added / stable path order."
        )

    if asset_has_location(keep_asset) and not asset_has_location(asset):
        return (
            "DELETE_CANDIDATE: same unique_id and same SHA256, "
            "but KEEP asset has location and this candidate does not."
        )

    return (
        "DELETE_CANDIDATE: same unique_id and same SHA256, "
        "but another candidate wins by earlier date_added / stable path order."
    )


def collect_field_values(group, field_name):
    values = []

    for asset in group:
        value = asset.get(field_name)

        if isinstance(value, (list, tuple)):
            value = tuple(value)

        if value not in values:
            values.append(value)

    return values


def group_shared_and_differing_fields(group):
    fields = [
        "original_filename",
        "date",
        "file_size_bytes",
        "content_sha256",
        "description",
        "keywords",
        "favorite",
        "hidden",
        "album_titles",
        "folder_paths",
        "location",
        "latitude",
        "longitude",
        "path_live_photo",
        "is_live_photo",
        "uuid",
        "filename",
        "date_added",
        "path",
    ]

    summarized_assets = [
        summarize_asset_for_report(asset)
        for asset in group
    ]

    shared_fields = {}
    differing_fields = {}

    for field_name in fields:
        values = collect_field_values(summarized_assets, field_name)

        if len(values) == 1:
            shared_fields[field_name] = values[0]
        else:
            differing_fields[field_name] = values

    return shared_fields, differing_fields


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

        # Safety-rule metadata.
        "latitude": asset.get("latitude"),
        "longitude": asset.get("longitude"),
        "location": asset_location_value(asset),
        "raw_location": asset.get("location"),
        "place": asset.get("place"),
        "is_live_photo": asset.get("is_live_photo"),
        "path_live_photo": asset.get("path_live_photo"),
        "live_photo_marker": repr(asset_live_photo_marker(asset)),

        # Keep-rule trace.
        "keep_sort_key": summarize_keep_sort_key(asset),
    }


def analyze_duplicate_candidate_groups(duplicate_candidate_groups):
    analysis = []
    total_groups = len(duplicate_candidate_groups)
    t0 = time.perf_counter()

    delete_decision_rule = {
        "rule_version": "duplicate_cleanup_v1",
        "deletable_condition": [
            "same photo_library_asset_unique_id",
            "readable original files",
            "successful SHA256 calculation",
            "same SHA256",
            "no Live Photo v1 exclusion",
            "no location conflict v1 exclusion",
        ],
        "keep_priority_order": [
            "prefer non-empty GPS/location",
            "prefer earliest date_added",
            "prefer stable path order",
        ],
        "matching_key_note": (
            "date_added is intentionally excluded from photo_library_asset_unique_id "
            "because export/import/repair operations can create a new date_added value."
        ),
    }

    for index, (unique_id, group) in enumerate(duplicate_candidate_groups.items(), start=1):
        if index % 10 == 0 or index == 1 or index == total_groups:
            print(f"Analyzing group {index}/{total_groups}")

        group_record = {
            "unique_id_repr": repr(unique_id),
            "asset_count": len(group),
            "status": None,
            "reason": None,
            "delete_decision_rule": delete_decision_rule,
            "safety_checks": {
                "live_photo_candidate": False,
                "location_conflict": False,
                "unreadable_original": False,
                "sha_error": False,
            },
            "location_values": location_values_for_group(group),
            "sha_groups": {},
            "shared_fields": {},
            "differing_fields": {},
            "keep_assets": [],
            "delete_candidates": [],
            "assets": [],
        }

        if any(asset_is_live_photo_candidate(asset) for asset in group):
            group_record["status"] = "REPORT_ONLY"
            group_record["reason"] = "LIVE_PHOTO_CANDIDATE_V1_SKIP_AUTO_DELETE"
            group_record["safety_checks"]["live_photo_candidate"] = True
            group_record["assets"] = [summarize_asset_for_report(asset) for asset in group]

            shared_fields, differing_fields = group_shared_and_differing_fields(group)
            group_record["shared_fields"] = shared_fields
            group_record["differing_fields"] = differing_fields

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
            group_record["safety_checks"]["unreadable_original"] = True
            group_record["assets"] = [summarize_asset_for_report(asset) for asset in group]

            shared_fields, differing_fields = group_shared_and_differing_fields(group)
            group_record["shared_fields"] = shared_fields
            group_record["differing_fields"] = differing_fields

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
            group_record["safety_checks"]["sha_error"] = True
            group_record["sha_errors"] = sha_errors
            group_record["assets"] = [summarize_asset_for_report(asset) for asset in group]

            shared_fields, differing_fields = group_shared_and_differing_fields(group)
            group_record["shared_fields"] = shared_fields
            group_record["differing_fields"] = differing_fields

            analysis.append(group_record)
            continue

        if group_has_location_conflict(group):
            group_record["status"] = "REPORT_ONLY"
            group_record["reason"] = "LOCATION_CONFLICT_V1_SKIP_AUTO_DELETE"
            group_record["safety_checks"]["location_conflict"] = True
            group_record["location_values"] = location_values_for_group(group)
            group_record["assets"] = [summarize_asset_for_report(asset) for asset in group]

            shared_fields, differing_fields = group_shared_and_differing_fields(group)
            group_record["shared_fields"] = shared_fields
            group_record["differing_fields"] = differing_fields

            for sha256, sha_group in sha_to_assets.items():
                group_record["sha_groups"][sha256] = [
                    summarize_asset_for_report(asset)
                    for asset in sha_group
                ]

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

            shared_fields, differing_fields = group_shared_and_differing_fields(group)
            group_record["shared_fields"] = shared_fields
            group_record["differing_fields"] = differing_fields

            analysis.append(group_record)
            continue

        group_record["status"] = "DELETABLE_DUPLICATE"
        group_record["reason"] = "SAME_UNIQUE_ID_AND_SAME_SHA256"

        delete_candidates = []
        keep_assets = []
        all_assets_with_decision = []

        for sha256, sha_group in deletable_sha_groups.items():
            sorted_group = stable_sort_assets_for_keep(sha_group)
            keep_asset = sorted_group[0]
            delete_assets = sorted_group[1:]

            for rank, asset in enumerate(sorted_group):
                asset["decision_role"] = "KEEP" if rank == 0 else "DELETE_CANDIDATE"
                asset["keep_sort_rank"] = rank
                asset["keep_decision_reason"] = summarize_keep_decision_reason(
                    asset=asset,
                    keep_asset=keep_asset,
                )

            keep_assets.append(keep_asset)
            delete_candidates.extend(delete_assets)
            all_assets_with_decision.extend(sorted_group)

        group_record["keep_assets"] = [summarize_asset_for_report(asset) for asset in keep_assets]
        group_record["delete_candidates"] = [summarize_asset_for_report(asset) for asset in delete_candidates]
        group_record["assets"] = [summarize_asset_for_report(asset) for asset in all_assets_with_decision]

        for asset in group_record["keep_assets"]:
            asset["decision_role"] = "KEEP"

        for asset in group_record["delete_candidates"]:
            asset["decision_role"] = "DELETE_CANDIDATE"

        for asset in group_record["assets"]:
            matching_source = next(
                (
                    source_asset
                    for source_asset in all_assets_with_decision
                    if source_asset.get("uuid") == asset.get("uuid")
                ),
                None,
            )

            if matching_source is not None:
                asset["decision_role"] = matching_source.get("decision_role")
                asset["keep_sort_rank"] = matching_source.get("keep_sort_rank")
                asset["keep_decision_reason"] = matching_source.get("keep_decision_reason")

        shared_fields, differing_fields = group_shared_and_differing_fields(all_assets_with_decision)
        group_record["shared_fields"] = shared_fields
        group_record["differing_fields"] = differing_fields

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


def stringify_tsv_value(value):
    if value is None:
        return ""

    if isinstance(value, (list, tuple)):
        return " | ".join(str(item) for item in value)

    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    return str(value)


def make_asset_report_row(group_index, record, asset, decision_role=None):
    role = decision_role or asset.get("decision_role") or ""

    return {
        "group_index": group_index,
        "group_status": record.get("status"),
        "group_reason": record.get("reason"),
        "decision_role": role,
        "keep_sort_rank": asset.get("keep_sort_rank"),
        "keep_decision_reason": asset.get("keep_decision_reason"),

        "original_filename": asset.get("original_filename"),
        "date": asset.get("date"),
        "date_added": asset.get("date_added"),
        "uuid": asset.get("uuid"),
        "filename": asset.get("filename"),
        "asset_scope": asset.get("asset_scope"),
        "path": asset.get("path"),

        "file_size_bytes": asset.get("file_size_bytes"),
        "content_sha256": asset.get("content_sha256"),

        "has_location": bool(asset.get("location")),
        "location": asset.get("location"),
        "latitude": asset.get("latitude"),
        "longitude": asset.get("longitude"),
        "raw_location": stringify_tsv_value(asset.get("raw_location")),
        "place": stringify_tsv_value(asset.get("place")),

        "is_live_photo": asset.get("is_live_photo"),
        "path_live_photo": asset.get("path_live_photo"),
        "live_photo_marker": asset.get("live_photo_marker"),

        "description": asset.get("description"),
        "keywords": stringify_tsv_value(asset.get("keywords") or []),
        "favorite": asset.get("favorite"),
        "hidden": asset.get("hidden"),
        "album_titles": stringify_tsv_value(asset.get("album_titles") or []),
        "folder_paths": stringify_tsv_value(asset.get("folder_paths") or []),

        "safety_checks": stringify_tsv_value(record.get("safety_checks") or {}),
        "location_values": stringify_tsv_value(record.get("location_values") or []),
    }


def flatten_delete_candidate_rows(records):
    rows = []

    for group_index, record in enumerate(records, start=1):
        for asset in record.get("delete_candidates") or []:
            rows.append(
                make_asset_report_row(
                    group_index=group_index,
                    record=record,
                    asset=asset,
                    decision_role="DELETE_CANDIDATE",
                )
            )

    return rows


def flatten_keep_asset_rows(records):
    rows = []

    for group_index, record in enumerate(records, start=1):
        for asset in record.get("keep_assets") or []:
            rows.append(
                make_asset_report_row(
                    group_index=group_index,
                    record=record,
                    asset=asset,
                    decision_role="KEEP",
                )
            )

    return rows


def flatten_duplicate_review_asset_rows(records):
    rows = []

    for group_index, record in enumerate(records, start=1):
        for asset in record.get("assets") or []:
            rows.append(
                make_asset_report_row(
                    group_index=group_index,
                    record=record,
                    asset=asset,
                    decision_role=asset.get("decision_role"),
                )
            )

    return rows


def flatten_location_conflict_rows(records):
    rows = []

    for group_index, record in enumerate(records, start=1):
        safety_checks = record.get("safety_checks") or {}

        if not safety_checks.get("location_conflict"):
            continue

        for asset in record.get("assets") or []:
            row = make_asset_report_row(
                group_index=group_index,
                record=record,
                asset=asset,
                decision_role=asset.get("decision_role"),
            )

            row["location_conflict_reason"] = "LOCATION_CONFLICT_V1_SKIP_AUTO_DELETE"
            row["all_location_values_in_group"] = stringify_tsv_value(
                record.get("location_values") or []
            )

            rows.append(row)

    return rows


def flatten_live_photo_candidate_rows(records):
    rows = []

    for group_index, record in enumerate(records, start=1):
        safety_checks = record.get("safety_checks") or {}

        if not safety_checks.get("live_photo_candidate"):
            continue

        for asset in record.get("assets") or []:
            row = make_asset_report_row(
                group_index=group_index,
                record=record,
                asset=asset,
                decision_role=asset.get("decision_role"),
            )

            row["live_photo_reason"] = "LIVE_PHOTO_CANDIDATE_V1_SKIP_AUTO_DELETE"

            rows.append(row)

    return rows


def flatten_assets_without_unique_id_rows(assets_without_unique_id):
    rows = []

    for asset in assets_without_unique_id:
        summarized_asset = summarize_asset_for_report(asset)

        missing_reasons = []

        if asset.get("original_filename") is None:
            missing_reasons.append("missing original_filename")

        if format_no_year_taipei_datetime(asset.get("date")) is None:
            missing_reasons.append("missing/invalid date")

        if asset.get("file_size_bytes") is None:
            missing_reasons.append("missing file_size_bytes")

        if not missing_reasons:
            missing_reasons.append("unknown missing unique_id reason")

        rows.append({
            "uuid": summarized_asset.get("uuid"),
            "original_filename": summarized_asset.get("original_filename"),
            "filename": summarized_asset.get("filename"),
            "date": summarized_asset.get("date"),
            "date_added": summarized_asset.get("date_added"),
            "asset_scope": summarized_asset.get("asset_scope"),
            "path": summarized_asset.get("path"),
            "file_size_bytes": summarized_asset.get("file_size_bytes"),

            "missing_reason": " | ".join(missing_reasons),

            "has_location": bool(summarized_asset.get("location")),
            "location": summarized_asset.get("location"),
            "latitude": summarized_asset.get("latitude"),
            "longitude": summarized_asset.get("longitude"),
            "raw_location": stringify_tsv_value(summarized_asset.get("raw_location")),
            "place": stringify_tsv_value(summarized_asset.get("place")),

            "is_live_photo": summarized_asset.get("is_live_photo"),
            "path_live_photo": summarized_asset.get("path_live_photo"),
            "live_photo_marker": summarized_asset.get("live_photo_marker"),

            "description": summarized_asset.get("description"),
            "keywords": stringify_tsv_value(summarized_asset.get("keywords") or []),
            "favorite": summarized_asset.get("favorite"),
            "hidden": summarized_asset.get("hidden"),
            "album_titles": stringify_tsv_value(summarized_asset.get("album_titles") or []),
            "folder_paths": stringify_tsv_value(summarized_asset.get("folder_paths") or []),
        })

    return rows


DUPLICATE_REVIEW_TSV_FIELDS = [
    "group_index",
    "group_status",
    "group_reason",
    "decision_role",
    "keep_sort_rank",
    "keep_decision_reason",

    "original_filename",
    "date",
    "date_added",
    "uuid",
    "filename",
    "asset_scope",
    "path",

    "file_size_bytes",
    "content_sha256",

    "has_location",
    "location",
    "latitude",
    "longitude",
    "raw_location",
    "place",

    "is_live_photo",
    "path_live_photo",
    "live_photo_marker",

    "description",
    "keywords",
    "favorite",
    "hidden",
    "album_titles",
    "folder_paths",

    "safety_checks",
    "location_values",
]


ASSETS_WITHOUT_UNIQUE_ID_TSV_FIELDS = [
    "uuid",
    "original_filename",
    "filename",
    "date",
    "date_added",
    "asset_scope",
    "path",
    "file_size_bytes",

    "missing_reason",

    "has_location",
    "location",
    "latitude",
    "longitude",
    "raw_location",
    "place",

    "is_live_photo",
    "path_live_photo",
    "live_photo_marker",

    "description",
    "keywords",
    "favorite",
    "hidden",
    "album_titles",
    "folder_paths",
]


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
    duplicate_review_asset_rows = flatten_duplicate_review_asset_rows(duplicate_analysis)
    location_conflict_rows = flatten_location_conflict_rows(duplicate_analysis)
    live_photo_candidate_rows = flatten_live_photo_candidate_rows(duplicate_analysis)
    assets_without_unique_id_rows = flatten_assets_without_unique_id_rows(assets_without_unique_id)

    status_counts = count_records_by_status(duplicate_analysis)

    safety_counts = {
        "live_photo_candidate_group_count": sum(
            1
            for record in duplicate_analysis
            if (record.get("safety_checks") or {}).get("live_photo_candidate")
        ),
        "location_conflict_group_count": sum(
            1
            for record in duplicate_analysis
            if (record.get("safety_checks") or {}).get("location_conflict")
        ),
        "unreadable_original_group_count": sum(
            1
            for record in duplicate_analysis
            if (record.get("safety_checks") or {}).get("unreadable_original")
        ),
        "sha_error_group_count": sum(
            1
            for record in duplicate_analysis
            if (record.get("safety_checks") or {}).get("sha_error")
        ),
    }

    write_json(report_dir / "duplicate_analysis.json", duplicate_analysis)
    write_json(report_dir / "kept_assets.json", keep_asset_rows)
    write_json(report_dir / "delete_candidates.json", delete_candidate_rows)
    write_json(report_dir / "duplicate_review_assets.json", duplicate_review_asset_rows)
    write_json(report_dir / "assets_without_unique_id.json", assets_without_unique_id_rows)

    write_tsv(
        report_dir / "duplicate_review_assets.tsv",
        duplicate_review_asset_rows,
        DUPLICATE_REVIEW_TSV_FIELDS,
    )

    write_tsv(
        report_dir / "delete_candidates.tsv",
        delete_candidate_rows,
        DUPLICATE_REVIEW_TSV_FIELDS,
    )

    write_tsv(
        report_dir / "kept_assets.tsv",
        keep_asset_rows,
        DUPLICATE_REVIEW_TSV_FIELDS,
    )

    write_tsv(
        report_dir / "location_conflicts.tsv",
        location_conflict_rows,
        DUPLICATE_REVIEW_TSV_FIELDS + [
            "location_conflict_reason",
            "all_location_values_in_group",
        ],
    )

    write_tsv(
        report_dir / "live_photo_candidates.tsv",
        live_photo_candidate_rows,
        DUPLICATE_REVIEW_TSV_FIELDS + [
            "live_photo_reason",
        ],
    )

    write_tsv(
        report_dir / "assets_without_unique_id.tsv",
        assets_without_unique_id_rows,
        ASSETS_WITHOUT_UNIQUE_ID_TSV_FIELDS,
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

safety_counts:
{json.dumps(safety_counts, ensure_ascii=False, indent=2)}

delete_candidate_asset_count: {len(delete_candidate_rows)}
keep_asset_count: {len(keep_asset_rows)}
duplicate_review_asset_count: {len(duplicate_review_asset_rows)}
location_conflict_row_count: {len(location_conflict_rows)}
live_photo_candidate_row_count: {len(live_photo_candidate_rows)}
assets_without_unique_id_row_count: {len(assets_without_unique_id_rows)}

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
        "duplicate_review_asset_rows": duplicate_review_asset_rows,
        "location_conflict_rows": location_conflict_rows,
        "live_photo_candidate_rows": live_photo_candidate_rows,
        "assets_without_unique_id_rows": assets_without_unique_id_rows,
        "status_counts": status_counts,
        "safety_counts": safety_counts,
    }
