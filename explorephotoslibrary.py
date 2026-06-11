# ============================================================
# explorephotoslibrary.py
#
# Consolidated helper module for the iCloud Photos Library
# forensic / metadata-based merge project.
#
# This file merges the previous photos_inventory.py and
# photos_duplicate_cleanup_helpers.py logic so notebooks import
# one module and use one shared identity scheme.
# ============================================================

import csv
import gzip
import hashlib
import json
import os
import pickle
import shutil
import subprocess
import time
from collections import defaultdict, Counter
from datetime import datetime
from enum import Enum
from pathlib import Path
from zoneinfo import ZoneInfo

__all__ = [
    # Inventory building / cache / search
    "build_inventory",
    "print_inventory_summary",
    "classify_asset_path_scope",
    "fill_photo_library_asset_unique_ids",
    "audit_photo_library_asset_unique_ids",
    "find_folders_by_title_keyword",
    "find_albums_by_title_keyword",
    "find_assets_by_description_keyword",
    "find_albums_under_folder",
    "find_albums_under_folder_title",
    "check_album_titles_exist_in_inventory",
    "save_inventory_cache",
    "load_inventory_cache",

    # Local file/folder picker and small config helpers
    "load_json_file",
    "save_json_file",
    "choose_directory_path",
    "choose_photos_library_path",

    # Cross-library comparison / missing-current review
    "compare_inventories",
    "summarize_diff_records",
    "filter_diff_records",
    "print_missing_current_review",
    "write_missing_current_review_report",
    "print_missing_current_review_report_summary",

    # Duplicate cleanup / review report pipeline
    "fill_duplicate_cleanup_identity_fields",
    "group_assets_by_field",
    "analyze_duplicate_candidate_groups",
    "count_records_by_status",
    "write_operation_report",
]


# ------------------------------------------------------------
# Internal basic helpers
# ------------------------------------------------------------

def _to_iso_string(value):
    # Convert datetime-like value to string.
    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)

def _to_serializable_string(value):
    # Convert osxphotos objects / metadata values into a stable string
    # for inventory snapshots and reports.
    #
    # Used for location/place-like objects whose exact type may vary by
    # osxphotos version or Photos database content.
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (list, tuple)):
        return tuple(
            _to_serializable_string(item)
            for item in value
        )

    if isinstance(value, dict):
        return {
            str(key): _to_serializable_string(item)
            for key, item in value.items()
        }

    if hasattr(value, "asdict"):
        try:
            return _to_serializable_string(value.asdict())
        except Exception:
            pass

    if hasattr(value, "_asdict"):
        try:
            return _to_serializable_string(value._asdict())
        except Exception:
            pass

    return repr(value)

def _get_attr(obj, name, default=None):
    # Safely get an attribute from an osxphotos object.
    if not hasattr(obj, name):
        return default

    value = getattr(obj, name)

    if callable(value):
        return value()

    return value

def _get_asset_local_file_status(osx_asset, path):
    # Classify this Photos asset for inventory routing.
    #
    # Rule:
    # - syndicated is an osxphotos / Photos database flag.
    # - If osxphotos says syndicated=True, trust the flag.
    # - Only when syndicated=False do we inspect path to decide whether this
    #   is a normal local original, path-none, or unknown path structure.
    syndicated = bool(_get_attr(osx_asset, "syndicated", default=False))

    if syndicated:
        return "SYNDICATED"

    if path is None:
        return "PATH_NONE"

    path_string = str(path)

    if "/scopes/syndication/" in path_string:
        return "UNKNOWN_PATH"

    if "/originals/" in path_string:
        return "NORMAL"

    return "UNKNOWN_PATH"

def _get_local_file_status_from_path(path):
    # Path-only fallback for older cached inventory objects or old callers.
    # Core inventory build should use _get_asset_local_file_status(), because
    # only the osxphotos asset object has the authoritative syndicated flag.
    if path is None:
        return "PATH_NONE"

    path_string = str(path)

    if "/scopes/syndication/" in path_string:
        return "SYNDICATED"

    if "/originals/" in path_string:
        return "NORMAL"

    return "UNKNOWN_PATH"

def get_asset_local_file_status(asset):
    # Public helper for already-built inventory asset dictionaries.
    return (
        asset.get("local_file_status")
        or asset.get("asset_scope")
        or _get_local_file_status_from_path(asset.get("path"))
    )


def classify_asset_path_scope(asset):
    # Backward-compatible wrapper for older notebook cells.
    return get_asset_local_file_status(asset)

# ------------------------------------------------------------
# Internal Photo Library asset unique ID helpers
# ------------------------------------------------------------

_PHOTO_LIBRARY_ASSET_UNIQUE_ID_TIMEZONE = ZoneInfo("Asia/Taipei")


def _parse_datetime_value(value):
    # Parse datetime-like values used by inventory assets.
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    return datetime.fromisoformat(str(value))


def _to_taipei_datetime(value):
    # Convert datetime-like value to Asia/Taipei timezone.
    dt = _parse_datetime_value(value)

    if dt is None:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=_PHOTO_LIBRARY_ASSET_UNIQUE_ID_TIMEZONE)

    return dt.astimezone(_PHOTO_LIBRARY_ASSET_UNIQUE_ID_TIMEZONE)


def _format_no_year_taipei_datetime(value):
    dt = _to_taipei_datetime(value)

    if dt is None:
        return None

    centisecond = dt.microsecond // 10000

    return (
        f"{dt.month:02d}-"
        f"{dt.day:02d} "
        f"{dt.hour:02d}:"
        f"{dt.minute:02d}:"
        f"{dt.second:02d}."
        f"{centisecond:02d}"
    )

def _format_full_taipei_datetime(value):
    # Format full date_added for matching.
    dt = _to_taipei_datetime(value)

    if dt is None:
        return None

    return (
        f"{dt.year:04d}-"
        f"{dt.month:02d}-"
        f"{dt.day:02d} "
        f"{dt.hour:02d}:"
        f"{dt.minute:02d}:"
        f"{dt.second:02d}."
        f"{dt.microsecond:06d}"
    )


def _make_photo_library_asset_unique_id(
    original_filename,
    filename,
    date,
    file_size,
    adjustment_signature,
    sha256=None,
):
    original_filename = original_filename or filename
    date = _format_no_year_taipei_datetime(date)

    if original_filename is None or date is None or file_size is None:
        return None

    return (
        original_filename,
        date,
        file_size,
        adjustment_signature,
        sha256,
    )

def finalize_photo_library_asset_unique_ids(inventory):
    first_four_to_assets = defaultdict(list)

    for asset in inventory["assets"]:
        file_size = _get_file_size_from_asset(asset)
        adjustment_signature = _make_adjustment_signature(asset)

        unique_id = _make_photo_library_asset_unique_id(
            original_filename=asset.get("original_filename"),
            filename=asset.get("filename"),
            date=asset.get("date"),
            file_size=file_size,
            adjustment_signature=adjustment_signature,
            sha256=None,
        )

        if unique_id is None:
            print("FATAL: cannot create photo_library_asset_unique_id")
            print(json.dumps(asset, ensure_ascii=False, indent=2, default=str))
            raise RuntimeError("Cannot create photo_library_asset_unique_id")

        asset["photo_library_asset_unique_id"] = unique_id
        first_four_to_assets[unique_id[:4]].append(asset)

    for first_four, group in first_four_to_assets.items():
        if len(group) <= 1:
            continue

        for asset in group:
            path = asset.get("path")

            if path is None:
                print("FATAL: SHA required but asset path is None")
                print("first four:", first_four)
                print(json.dumps(asset, ensure_ascii=False, indent=2, default=str))
                raise RuntimeError("SHA required but asset path is None")

            if not os.path.exists(path):
                print("FATAL: SHA required but asset path does not exist")
                print("first four:", first_four)
                print(json.dumps(asset, ensure_ascii=False, indent=2, default=str))
                raise RuntimeError("SHA required but asset path does not exist")

            sha256 = _sha256_file(path)

            asset["photo_library_asset_unique_id"] = (
                first_four[0],
                first_four[1],
                first_four[2],
                first_four[3],
                sha256,
            )

    final_unique_id_to_assets = defaultdict(list)

    for asset in inventory["assets"]:
        final_unique_id_to_assets[asset["photo_library_asset_unique_id"]].append(asset)

    for unique_id, group in final_unique_id_to_assets.items():
        if len(group) <= 1:
            continue

        print("FATAL: photo_library_asset_unique_id collision")
        print("photo_library_asset_unique_id:", unique_id)
        print("asset count:", len(group))

        for asset in group:
            print(json.dumps(asset, ensure_ascii=False, indent=2, default=str))

        raise RuntimeError("photo_library_asset_unique_id collision")

    return inventory

def _get_file_size_from_asset(asset):
    path = asset.get("path")

    if path is None:
        return None

    try:
        return os.path.getsize(path)
    except OSError:
        return None


def _get_file_size_bytes_from_asset(asset):
    # Backward-compatible wrapper for old notebook/helper callers.
    return _get_file_size_from_asset(asset)

def _get_edited_duration_seconds_from_asset(asset):
    if not asset.get("is_movie"):
        return None

    if not asset.get("hasadjustments"):
        return None

    path_edited = asset.get("path_edited")

    if path_edited is None:
        return None

    if not os.path.exists(path_edited):
        return None

    ffprobe = shutil.which("ffprobe")

    if ffprobe is None:
        return None

    command = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        str(path_edited),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return None

    try:
        data = json.loads(result.stdout)
        duration = data.get("format", {}).get("duration")

        if duration is None:
            return None

        return round(float(duration), 6)

    except Exception:
        return None

def _make_adjustment_signature(asset):
    if not asset.get("hasadjustments"):
        return None

    if asset.get("is_movie"):
        edited_duration_seconds = _get_edited_duration_seconds_from_asset(asset)

        if edited_duration_seconds is None:
            return None

        return round(float(edited_duration_seconds), 1)

    width = asset.get("width")
    height = asset.get("height")

    if width is None or height is None:
        return None

    return (
        int(width),
        int(height),
    )

def _folder_path_from_titles(folder_titles):
    # Build human-readable folder path.
    return "/".join(folder_titles)


def _assert_same_field(existing_object, new_object, field_name, object_type):
    # Same UUID should not produce different metadata.
    if existing_object.get(field_name) != new_object.get(field_name):
        raise RuntimeError(
            f"{object_type} UUID same but {field_name} different.\n"
            f"uuid={existing_object.get('uuid')}\n"
            f"existing={existing_object}\n"
            f"new={new_object}"
        )


# ------------------------------------------------------------
# Internal object creators
# ------------------------------------------------------------

def _create_asset_object(osx_asset):
    path = str(osx_asset.path) if osx_asset.path else None
    local_file_status = _get_asset_local_file_status(osx_asset, path)

    syndicated = bool(_get_attr(osx_asset, "syndicated", default=False))
    saved_to_library = bool(_get_attr(osx_asset, "saved_to_library", default=False))
    ismissing = bool(_get_attr(osx_asset, "ismissing", default=False))
    original_filesize = _get_attr(osx_asset, "original_filesize", default=None)

    path_derivatives = _get_attr(osx_asset, "path_derivatives", default=[])
    path_derivatives = tuple(
        str(path_derivative)
        for path_derivative in (path_derivatives or [])
        if path_derivative
    )

    path_live_photo = _get_attr(osx_asset, "path_live_photo", default=None)
    path_live_photo = str(path_live_photo) if path_live_photo else None

    path_edited = _get_attr(osx_asset, "path_edited", default=None)
    path_edited = str(path_edited) if path_edited else None

    path_edited_live_photo = _get_attr(osx_asset, "path_edited_live_photo", default=None)
    path_edited_live_photo = str(path_edited_live_photo) if path_edited_live_photo else None

    live_photo_value = _get_attr(osx_asset, "live_photo", default=None)
    is_live_photo = bool(live_photo_value) or bool(path_live_photo)

    latitude = _get_attr(osx_asset, "latitude", default=None)
    longitude = _get_attr(osx_asset, "longitude", default=None)
    location = _get_attr(osx_asset, "location", default=None)
    place = _get_attr(osx_asset, "place", default=None)

    return {
        "uuid": osx_asset.uuid,

        "original_filename": osx_asset.original_filename,
        "filename": osx_asset.filename,
        "path": path,

        # Kept only so build_inventory() can route the asset.
        # NORMAL assets will have this removed before entering inventory["assets"].
        "local_file_status": local_file_status,

        # Kept for special_assets buckets only.
        # NORMAL assets will have these removed before entering inventory["assets"].
        "syndicated": syndicated,
        "saved_to_library": saved_to_library,
        "ismissing": ismissing,
        "original_filesize": original_filesize,
        "path_derivatives": path_derivatives,

        "is_movie": bool(osx_asset.ismovie),

        "date": _to_iso_string(osx_asset.date),
        "date_added": _to_iso_string(osx_asset.date_added),
        "date_modified": _to_iso_string(_get_attr(osx_asset, "date_modified", default=None)),

        "description": osx_asset.description,
        "keywords": tuple(osx_asset.keywords),
        "favorite": bool(osx_asset.favorite),
        "hidden": _get_attr(osx_asset, "hidden", default=None),

        "width": _get_attr(osx_asset, "width", default=None),
        "height": _get_attr(osx_asset, "height", default=None),
        "original_width": _get_attr(osx_asset, "original_width", default=None),
        "original_height": _get_attr(osx_asset, "original_height", default=None),

        "hasadjustments": bool(_get_attr(osx_asset, "hasadjustments", default=False)),
        "adjustment_type": _get_attr(osx_asset, "adjustment_type", default=None),
        "external_edit": bool(_get_attr(osx_asset, "external_edit", default=False)),
        "uti": _get_attr(osx_asset, "uti", default=None),
        "uti_original": _get_attr(osx_asset, "uti_original", default=None),
        "uti_edited": _get_attr(osx_asset, "uti_edited", default=None),

        "path_edited": path_edited,
        "path_live_photo": path_live_photo,
        "path_edited_live_photo": path_edited_live_photo,
        "is_live_photo": is_live_photo,

        "latitude": latitude,
        "longitude": longitude,
        "location": _to_serializable_string(location),
        "place": _to_serializable_string(place),

        "albums": {},
        "folders": {},

        # Finalized during build_inventory().
        "photo_library_asset_unique_id": None,
    }

def _create_album_object(album_info):
    # Create one Album object from one osxphotos AlbumInfo object.
    return {
        "uuid": album_info.uuid,
        "title": album_info.title,

        "folders": {},  # folder_uuid -> Folder object
    }


def _create_folder_object(folder_info, folder_path):
    # Create one Folder object from one osxphotos FolderInfo object.
    return {
        "uuid": folder_info.uuid,
        "title": folder_info.title,
        "path": folder_path,
    }


# ------------------------------------------------------------
# Internal get_or_create helpers
# ------------------------------------------------------------

def _get_or_create_album(inventory, album_info):
    # Get existing Album object or create a new one.
    album_uuid = album_info.uuid
    new_album = _create_album_object(album_info)

    if album_uuid not in inventory["albums"]:
        inventory["albums"][album_uuid] = new_album
        return new_album

    existing_album = inventory["albums"][album_uuid]

    _assert_same_field(existing_album, new_album, "title", "Album")

    return existing_album


def _get_or_create_folder(inventory, folder_info, folder_path):
    # Get existing Folder object or create a new one.
    folder_uuid = folder_info.uuid
    new_folder = _create_folder_object(folder_info, folder_path)

    if folder_uuid not in inventory["folders"]:
        inventory["folders"][folder_uuid] = new_folder
        return new_folder

    existing_folder = inventory["folders"][folder_uuid]

    _assert_same_field(existing_folder, new_folder, "title", "Folder")
    _assert_same_field(existing_folder, new_folder, "path", "Folder")

    return existing_folder


def _get_folder_objects_from_album_info(inventory, album_info):
    # Convert album_info.folder_list into Folder objects.
    folder_list = list(_get_attr(album_info, "folder_list", default=[]))
    folder_names = list(_get_attr(album_info, "folder_names", default=[]))

    folder_titles = [
        folder_info.title
        for folder_info in folder_list
    ]

    if folder_names and folder_titles and folder_names != folder_titles:
        raise RuntimeError(
            "folder_names and folder_list titles are different.\n"
            f"album_uuid={album_info.uuid}\n"
            f"album_title={album_info.title}\n"
            f"folder_names={folder_names}\n"
            f"folder_titles={folder_titles}"
        )

    folder_objects = {}
    folder_titles_so_far = []

    for folder_info in folder_list:
        folder_titles_so_far.append(folder_info.title)
        folder_path = _folder_path_from_titles(folder_titles_so_far)

        folder = _get_or_create_folder(
            inventory=inventory,
            folder_info=folder_info,
            folder_path=folder_path,
        )

        folder_objects[folder["uuid"]] = folder

    return folder_objects


# ------------------------------------------------------------
# Public inventory builder
# ------------------------------------------------------------

def build_inventory(osx_assets):
    inventory = {
        "assets": [],
        "special_assets": {
            "SYNDICATED": [],
            "PATH_NONE": [],
            "UNKNOWN_PATH": [],
        },
        "albums": {},
        "folders": {},
        "errors": [],
    }

    seen_asset_uuids = set()
    seen_special_asset_uuids = set()

    for index, osx_asset in enumerate(osx_assets, start=1):
        asset = _create_asset_object(osx_asset)
        asset_uuid = asset["uuid"]
        local_file_status = asset.get("local_file_status")

        if local_file_status != "NORMAL":
            if asset_uuid in seen_special_asset_uuids:
                raise RuntimeError(f"Duplicate special asset UUID: {asset_uuid}")

            seen_special_asset_uuids.add(asset_uuid)
            inventory["special_assets"][local_file_status].append(asset)

            if index % 10000 == 0:
                print("processed assets:", index)

            continue

        if asset_uuid in seen_asset_uuids:
            raise RuntimeError(f"Duplicate asset UUID: {asset_uuid}")

        seen_asset_uuids.add(asset_uuid)

        # NORMAL assets do not need local-file-status / special-state fields.
        asset.pop("local_file_status", None)
        asset.pop("syndicated", None)
        asset.pop("saved_to_library", None)
        asset.pop("ismissing", None)
        asset.pop("original_filesize", None)
        asset.pop("path_derivatives", None)

        for album_info in osx_asset.album_info:
            album = _get_or_create_album(
                inventory=inventory,
                album_info=album_info,
            )

            asset["albums"][album["uuid"]] = album

            folder_objects = _get_folder_objects_from_album_info(
                inventory=inventory,
                album_info=album_info,
            )

            for folder_uuid, folder in folder_objects.items():
                asset["folders"][folder_uuid] = folder
                album["folders"][folder_uuid] = folder

        inventory["assets"].append(asset)

        if index % 10000 == 0:
            print("processed assets:", index)

    finalize_photo_library_asset_unique_ids(inventory)

    return inventory

# ------------------------------------------------------------
# Public inventory summary
# ------------------------------------------------------------

def print_inventory_summary(inventory):
    # Print basic inventory counts and metadata counts.
    print("inventory assets:", len(inventory["assets"]))
    print("inventory albums:", len(inventory["albums"]))
    print("inventory folders:", len(inventory["folders"]))

    special_assets = inventory.get("special_assets") or {}

    if special_assets:
        print("special assets:")
        for scope, assets in sorted(special_assets.items()):
            print(f"  {scope}: {len(assets)}")

    hidden_count = sum(
        1
        for asset in inventory["assets"]
        if asset["hidden"] is True
    )

    favorite_count = sum(
        1
        for asset in inventory["assets"]
        if asset["favorite"] is True
    )

    description_count = sum(
        1
        for asset in inventory["assets"]
        if asset["description"]
    )

    keyword_count = sum(
        1
        for asset in inventory["assets"]
        if asset["keywords"]
    )

    movie_count = sum(
        1
        for asset in inventory["assets"]
        if asset["is_movie"]
    )

    print("movies:", movie_count)
    print("hidden:", hidden_count)
    print("favorites:", favorite_count)
    print("descriptions:", description_count)
    print("keywords:", keyword_count)

# ------------------------------------------------------------
# Public Photo Library asset unique ID helpers
# ------------------------------------------------------------

def fill_photo_library_asset_unique_ids(inventory):
    # Backward-compatible wrapper for old notebook cells.
    return finalize_photo_library_asset_unique_ids(inventory)

def audit_photo_library_asset_unique_ids(
    inventory,
    label="Photos Library",
    max_duplicate_groups_to_print=20,
):
    # Check whether photo_library_asset_unique_id is unique inside one library.
    key_to_assets = {}
    assets_without_unique_id = []

    for asset in inventory["assets"]:
        unique_id = asset.get("photo_library_asset_unique_id")

        if unique_id is None:
            assets_without_unique_id.append(asset)
            continue

        if unique_id not in key_to_assets:
            key_to_assets[unique_id] = []

        key_to_assets[unique_id].append(asset)

    duplicate_groups = {
        unique_id: group
        for unique_id, group in key_to_assets.items()
        if len(group) > 1
    }

    duplicate_asset_count = sum(
        len(group)
        for group in duplicate_groups.values()
    )

    is_unique = (
        len(assets_without_unique_id) == 0
        and len(duplicate_groups) == 0
    )

    print(label)
    print("-" * 80)
    print("total asset count:", len(inventory["assets"]))
    print("generated unique ID count:", len(key_to_assets))
    print("assets without unique ID:", len(assets_without_unique_id))
    print("duplicate unique ID group count:", len(duplicate_groups))
    print("duplicate asset count:", duplicate_asset_count)
    print("is Photo Library asset unique ID scheme unique:", is_unique)

    if duplicate_groups:
        print()
        print("Duplicate unique ID groups")
        print("-" * 80)

        for index, (unique_id, group) in enumerate(duplicate_groups.items()):
            if index >= max_duplicate_groups_to_print:
                print("... more duplicate groups not printed")
                break

            print("photo_library_asset_unique_id:", unique_id)
            print("asset count:", len(group))

            for asset in group:
                print("  uuid:", asset["uuid"])
                print("  filename:", asset["filename"])
                print("  original_filename:", asset["original_filename"])
                print("  date:", asset["date"])
                print("  date_added:", asset["date_added"])
                print("  path:", asset["path"])

            print("-" * 80)

    return is_unique

# ------------------------------------------------------------
# Public search helpers
# ------------------------------------------------------------

def find_folders_by_title_keyword(inventory, keyword):
    # Find folders whose title contains keyword.
    matched_folders = []

    for folder in inventory["folders"].values():
        title = folder["title"] or ""

        if keyword in title:
            matched_folders.append(folder)

    return matched_folders


def find_albums_by_title_keyword(inventory, keyword):
    # Find albums whose title contains keyword.
    matched_albums = []

    for album in inventory["albums"].values():
        title = album["title"] or ""

        if keyword in title:
            matched_albums.append(album)

    return matched_albums


def find_assets_by_description_keyword(inventory, keyword):
    # Find assets whose description contains keyword.
    matched_assets = []

    for asset in inventory["assets"]:
        description = asset["description"] or ""

        if keyword in description:
            matched_assets.append(asset)

    return matched_assets


def find_albums_under_folder(inventory, folder):
    # Find albums that belong to the given Folder object.
    matched_albums = []

    for album in inventory["albums"].values():
        if folder["uuid"] in album["folders"]:
            matched_albums.append(album)

    return sorted(
        matched_albums,
        key=lambda album: album["title"] or ""
    )


def find_albums_under_folder_title(inventory, folder_title):
    # Find folders by exact title, then find albums under those folders.
    matched_folders = []

    for folder in inventory["folders"].values():
        if folder["title"] == folder_title:
            matched_folders.append(folder)

    matched_albums = []

    for folder in matched_folders:
        matched_albums.extend(
            find_albums_under_folder(inventory, folder)
        )

    return matched_folders, matched_albums


def check_album_titles_exist_in_inventory(album_titles, inventory):
    # Check whether album titles exist in another inventory.
    target_album_titles = {
        album["title"]
        for album in inventory["albums"].values()
    }

    found_titles = []
    missing_titles = []

    for title in album_titles:
        if title in target_album_titles:
            found_titles.append(title)
        else:
            missing_titles.append(title)

    return found_titles, missing_titles


# ------------------------------------------------------------
# Internal cache helper
# ------------------------------------------------------------

def _get_inventory_cache_path(cache_name, cache_dir="data/inventory_cache"):
    # Return cache file path for one inventory.
    return os.path.join(cache_dir, f"{cache_name}.inventory.pkl.gz")


# ------------------------------------------------------------
# Public cache helpers
# ------------------------------------------------------------

def save_inventory_cache(inventory, cache_name, cache_dir="data/inventory_cache"):
    # Save inventory to compressed pickle cache.
    os.makedirs(cache_dir, exist_ok=True)

    cache_path = _get_inventory_cache_path(
        cache_name=cache_name,
        cache_dir=cache_dir,
    )

    start_time = time.time()

    with gzip.open(cache_path, "wb") as f:
        pickle.dump(inventory, f, protocol=pickle.HIGHEST_PROTOCOL)

    elapsed = time.time() - start_time

    print("saved inventory cache:", cache_path)
    print("elapsed seconds:", round(elapsed, 2))

    return cache_path


def load_inventory_cache(cache_name, cache_dir="data/inventory_cache"):
    # Load inventory from compressed pickle cache.
    cache_path = _get_inventory_cache_path(
        cache_name=cache_name,
        cache_dir=cache_dir,
    )

    start_time = time.time()

    with gzip.open(cache_path, "rb") as f:
        inventory = pickle.load(f)

    elapsed = time.time() - start_time

    print("loaded inventory cache:", cache_path)
    print("elapsed seconds:", round(elapsed, 2))
    print_inventory_summary(inventory)

    return inventory

def load_json_file(path, default=None):
    # Load a JSON file. Return default if the file does not exist.
    path = os.fspath(path)

    if not os.path.exists(path):
        return default

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_file(path, data):
    # Save JSON with UTF-8 and readable indentation.
    path = os.fspath(path)
    parent = os.path.dirname(path)

    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def choose_directory_path(title="Select Folder", initial_dir=None):
    # Open a folder picker and return the selected folder path.
    #
    # On macOS, .photoslibrary is a package directory, so selecting it
    # should use askdirectory rather than askopenfilename.
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as error:
        raise RuntimeError(
            "tkinter is not available in this Python environment. "
            "Use a hard-coded path instead."
        ) from error

    root = tk.Tk()
    root.withdraw()
    root.update()

    selected_path = filedialog.askdirectory(
        title=title,
        initialdir=str(initial_dir or os.path.expanduser("~")),
    )

    root.destroy()

    if not selected_path:
        raise RuntimeError("No folder selected.")

    return selected_path


def choose_photos_library_path(initial_dir=None, prompt="Select Photos Library (.photoslibrary)"):
    # Open a macOS picker and return the selected .photoslibrary package path.
    #
    # .photoslibrary is a macOS package. AppleScript choose file works better
    # than tkinter.askdirectory for selecting this kind of package.
    #
    # prompt is optional so old notebook calls remain compatible.
    initial_dir = os.fspath(initial_dir or "/Volumes")

    if not os.path.exists(initial_dir):
        initial_dir = "/Volumes"

    applescript = '''
on run argv
    set initialFolderPath to item 1 of argv
    set pickerPrompt to item 2 of argv
    set initialFolder to POSIX file initialFolderPath
    set selectedItem to choose file with prompt pickerPrompt default location initialFolder
    return POSIX path of selectedItem
end run
'''

    result = subprocess.run(
        ["osascript", "-e", applescript, initial_dir, prompt],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "No Photos Library selected or picker failed.\n"
            f"stderr: {result.stderr.strip()}"
        )

    selected_path = result.stdout.strip()

    if not selected_path:
        raise RuntimeError("No Photos Library selected.")

    selected_path = selected_path.rstrip("/")

    if not selected_path.endswith(".photoslibrary"):
        raise RuntimeError(
            "Selected path does not end with .photoslibrary:\n"
            f"{selected_path}"
        )

    return selected_path

# ------------------------------------------------------------
# Duplicate cleanup / review report helpers
# ------------------------------------------------------------

def _normalize_text(value):
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    return text


def _normalize_string_tuple(values):
    if not values:
        return tuple()

    normalized = []
    for value in values:
        text = _normalize_text(value)
        if text is not None:
            normalized.append(text)

    return tuple(sorted(set(normalized)))


def _asset_album_titles(asset):
    albums = asset.get("albums") or {}
    titles = []

    for album in albums.values():
        title = album.get("title")
        if title:
            titles.append(title)

    return _normalize_string_tuple(titles)


def _asset_folder_paths(asset):
    folders = asset.get("folders") or {}
    paths = []

    for folder in folders.values():
        path = folder.get("path") or folder.get("title")
        if path:
            paths.append(path)

    return _normalize_string_tuple(paths)


def _make_duplicate_cleanup_asset_base_id(asset):
    original_filename = asset.get("original_filename")
    no_year_datetime = _format_no_year_taipei_datetime(asset.get("date"))
    file_size_bytes = asset.get("file_size_bytes")
    adjustment_signature = asset.get("adjustment_signature")

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
        adjustment_signature,
    )


def _make_duplicate_cleanup_canonical_ourmetadata(asset):
    return (
        ("description", _normalize_text(asset.get("description"))),
        ("keywords", _normalize_string_tuple(asset.get("keywords") or tuple())),
        ("favorite", bool(asset.get("favorite"))),
        ("hidden", bool(asset.get("hidden"))),
        ("album_titles", _asset_album_titles(asset)),
        ("folder_paths", _asset_folder_paths(asset)),
    )


def _make_duplicate_cleanup_asset_unique_id(asset):
    base_id = asset.get("photo_library_asset_base_id")
    if base_id is None:
        return None
    return (
        base_id,
        _make_duplicate_cleanup_canonical_ourmetadata(asset),
    )


def fill_duplicate_cleanup_identity_fields(inventory):
    reason_counter = Counter()

    for asset in inventory["assets"]:
        asset["file_size_bytes"] = _get_file_size_bytes_from_asset(asset)
        asset["edited_duration_seconds"] = _get_edited_duration_seconds_from_asset(asset)
        asset["adjustment_signature"] = _make_adjustment_signature(asset)

        base_id = _make_duplicate_cleanup_asset_base_id(asset)
        asset["photo_library_asset_base_id"] = base_id

        if base_id is None:
            if asset.get("original_filename") is None:
                reason_counter["missing original_filename"] += 1
            elif _format_no_year_taipei_datetime(asset.get("date")) is None:
                reason_counter["missing/invalid date"] += 1
            elif asset.get("file_size_bytes") is None:
                reason_counter["missing file_size_bytes"] += 1
            else:
                reason_counter["unknown base_id failure"] += 1

            asset["photo_library_asset_unique_id"] = None
            continue

        asset["photo_library_asset_unique_id"] = _make_duplicate_cleanup_asset_unique_id(asset)

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

    adjustment_signature_count = sum(
        1
        for asset in inventory["assets"]
        if asset.get("adjustment_signature") is not None
    )

    edited_duration_count = sum(
        1
        for asset in inventory["assets"]
        if asset.get("edited_duration_seconds") is not None
    )

    print("Filled identity fields")
    print("asset count:", len(inventory["assets"]))
    print("base_id filled:", base_id_count)
    print("unique_id filled:", unique_id_count)
    print("adjustment_signature filled:", adjustment_signature_count)
    print("edited_duration_seconds filled:", edited_duration_count)

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
        print("path_edited:", asset.get("path_edited"))
        print("file_size_bytes:", asset.get("file_size_bytes"))
        print("edited_duration_seconds:", asset.get("edited_duration_seconds"))
        print("adjustment_signature:", asset.get("adjustment_signature"))
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


def _sha256_file(path, chunk_size=1024 * 1024):
    sha256 = hashlib.sha256()

    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha256.update(chunk)

    return sha256.hexdigest()


def _calculate_asset_sha256(asset):
    path = asset.get("path")

    if path is None:
        return None, "PATH_NONE"

    if not os.path.exists(path):
        return None, "PATH_DOES_NOT_EXIST"

    try:
        sha256 = _sha256_file(path)
    except Exception as error:
        return None, f"SHA_ERROR: {error}"

    asset["content_sha256"] = sha256
    return sha256, None


def _asset_has_readable_original(asset):
    path = asset.get("path")
    return path is not None and os.path.exists(path)


def _get_first_present(asset, field_names):
    for field_name in field_names:
        if field_name in asset and asset.get(field_name) not in (None, "", tuple(), []):
            return asset.get(field_name)
    return None


def _asset_live_photo_marker(asset):
    return _get_first_present(
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


def _asset_is_live_photo_candidate(asset):
    marker = _asset_live_photo_marker(asset)

    if marker is None:
        return False

    if marker is False:
        return False

    return True


def _asset_location_value(asset):
    # Canonical location value for duplicate cleanup safety checks.
    #
    # Location is not part of photo_library_asset_unique_id.
    # It is used only for keep preference and conflict reporting.
    latitude = _get_first_present(asset, ["latitude", "lat"])
    longitude = _get_first_present(asset, ["longitude", "lon", "lng"])

    if latitude is not None and longitude is not None:
        return f"{latitude},{longitude}"

    location = _get_first_present(
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


def _asset_has_location(asset):
    return _asset_location_value(asset) is not None

def _get_existing_file_size(path):
    if path is None:
        return None

    if not os.path.exists(path):
        return None

    try:
        return os.path.getsize(path)
    except OSError:
        return None


def _adjustment_metadata_profile_for_duplicate_cleanup(asset):
    # Full adjustment metadata profile for duplicate cleanup safety.
    #
    # Important:
    # - This is NOT part of photo_library_asset_unique_id.
    # - photo_library_asset_unique_id is a matching/grouping key.
    # - This profile is a stricter deletion-safety check after:
    #     same photo_library_asset_unique_id + same original SHA256.
    #
    # Do not compare full absolute path_edited because Photos Libraries can
    # move between volumes. Compare existence and rendered file size instead.
    path_edited = asset.get("path_edited")
    path_edited_live_photo = asset.get("path_edited_live_photo")

    return (
        ("hasadjustments", bool(asset.get("hasadjustments"))),
        ("adjustment_type", asset.get("adjustment_type")),
        ("external_edit", bool(asset.get("external_edit"))),
        ("uti", asset.get("uti")),
        ("uti_original", asset.get("uti_original")),
        ("uti_edited", asset.get("uti_edited")),
        ("path_edited_exists", path_edited is not None),
        ("path_edited_file_size", _get_existing_file_size(path_edited)),
        ("path_edited_live_photo_exists", path_edited_live_photo is not None),
        ("path_edited_live_photo_file_size", _get_existing_file_size(path_edited_live_photo)),
        ("edited_duration_seconds", asset.get("edited_duration_seconds")),
        ("adjustment_signature", asset.get("adjustment_signature")),
        ("width", asset.get("width")),
        ("height", asset.get("height")),
        ("original_width", asset.get("original_width")),
        ("original_height", asset.get("original_height")),
    )


def _adjustment_metadata_profiles_for_group(group):
    profiles = []

    for asset in group:
        profile = _adjustment_metadata_profile_for_duplicate_cleanup(asset)

        if profile not in profiles:
            profiles.append(profile)

    return profiles


def _group_has_adjustment_metadata_mismatch(group):
    return len(_adjustment_metadata_profiles_for_group(group)) > 1

def _location_values_for_group(group):
    return sorted(
        set(
            _asset_location_value(asset)
            for asset in group
            if _asset_location_value(asset) is not None
        )
    )


def _group_has_location_conflict(group):
    # v1 safety rule:
    # If multiple non-empty location values exist inside one otherwise
    # deletable duplicate group, do not auto-delete. Report only.
    return len(_location_values_for_group(group)) > 1


def _keep_sort_key(asset):
    # v1 keep priority:
    # 1. Prefer non-empty GPS/location.
    # 2. Prefer earliest date_added.
    # 3. Prefer stable path order.
    has_location = _asset_has_location(asset)
    date_added = asset.get("date_added") or ""
    path = asset.get("path") or ""

    return (
        0 if has_location else 1,
        date_added,
        path,
    )


def _stable_sort_assets_for_keep(group):
    return sorted(group, key=_keep_sort_key)


def _summarize_keep_sort_key(asset):
    return {
        "has_location": _asset_has_location(asset),
        "location": _asset_location_value(asset),
        "date_added": asset.get("date_added"),
        "path": asset.get("path"),
    }


def _summarize_keep_decision_reason(asset, keep_asset):
    if asset.get("uuid") == keep_asset.get("uuid"):
        if _asset_has_location(asset):
            return (
                "KEEP: selected by v1 keep rule; candidate has location, "
                "then earliest date_added / stable path order."
            )

        return (
            "KEEP: selected by v1 keep rule; no location advantage found, "
            "then earliest date_added / stable path order."
        )

    if _asset_has_location(keep_asset) and not _asset_has_location(asset):
        return (
            "DELETE_CANDIDATE: same unique_id and same SHA256, "
            "but KEEP asset has location and this candidate does not."
        )

    return (
        "DELETE_CANDIDATE: same unique_id and same SHA256, "
        "but another candidate wins by earlier date_added / stable path order."
    )


def _collect_field_values(group, field_name):
    values = []

    for asset in group:
        value = asset.get(field_name)

        if isinstance(value, (list, tuple)):
            value = tuple(value)

        if value not in values:
            values.append(value)

    return values


def _group_shared_and_differing_fields(group):
    fields = [
        "original_filename",
        "date",
        "file_size_bytes",
        "content_sha256",

        "adjustment_signature",
        "hasadjustments",
        "edited_duration_seconds",
        "width",
        "height",
        "original_width",
        "original_height",
        "path_edited",

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
        _summarize_asset_for_report(asset)
        for asset in group
    ]

    shared_fields = {}
    differing_fields = {}

    for field_name in fields:
        values = _collect_field_values(summarized_assets, field_name)

        if len(values) == 1:
            shared_fields[field_name] = values[0]
        else:
            differing_fields[field_name] = values

    return shared_fields, differing_fields


def _summarize_asset_for_report(asset):
    return {
        "uuid": asset.get("uuid"),
        "original_filename": asset.get("original_filename"),
        "filename": asset.get("filename"),
        "date": asset.get("date"),
        "date_added": asset.get("date_added"),
        "date_modified": asset.get("date_modified"),
        "path": asset.get("path"),
        "asset_scope": asset.get("asset_scope"),
        "file_size_bytes": asset.get("file_size_bytes"),
        "content_sha256": asset.get("content_sha256"),

        # Adjustment metadata.
        "hasadjustments": asset.get("hasadjustments"),
        "adjustment_type": asset.get("adjustment_type"),
        "external_edit": asset.get("external_edit"),
        "uti_edited": asset.get("uti_edited"),
        "path_edited": asset.get("path_edited"),
        "path_edited_live_photo": asset.get("path_edited_live_photo"),
        "edited_duration_seconds": asset.get("edited_duration_seconds"),
        "adjustment_signature": asset.get("adjustment_signature"),

        # Photos-visible dimensions.
        "width": asset.get("width"),
        "height": asset.get("height"),
        "original_width": asset.get("original_width"),
        "original_height": asset.get("original_height"),
        "is_movie": asset.get("is_movie"),

        "description": asset.get("description"),
        "keywords": list(asset.get("keywords") or []),
        "favorite": asset.get("favorite"),
        "hidden": asset.get("hidden"),
        "album_titles": list(_asset_album_titles(asset)),
        "folder_paths": list(_asset_folder_paths(asset)),

        # Safety-rule metadata.
        "latitude": asset.get("latitude"),
        "longitude": asset.get("longitude"),
        "location": _asset_location_value(asset),
        "raw_location": asset.get("location"),
        "place": asset.get("place"),
        "is_live_photo": asset.get("is_live_photo"),
        "path_live_photo": asset.get("path_live_photo"),
        "live_photo_marker": repr(_asset_live_photo_marker(asset)),

        # Keep-rule trace.
        "keep_sort_key": _summarize_keep_sort_key(asset),
    }


def analyze_duplicate_candidate_groups(duplicate_candidate_groups):
    analysis = []
    total_groups = len(duplicate_candidate_groups)
    t0 = time.perf_counter()

    delete_decision_rule = {
        "rule_version": "duplicate_cleanup_v2",
        "deletable_condition": [
            "same photo_library_asset_unique_id",
            "readable original files",
            "successful SHA256 calculation",
            "same original SHA256",
            "same full adjustment metadata profile",
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
        "adjustment_metadata_note": (
            "adjustment_signature is part of the matching identity key, but duplicate cleanup "
            "also requires a full adjustment metadata profile match before a same-SHA group "
            "can be marked as DELETABLE_DUPLICATE."
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
                "adjustment_metadata_mismatch": False,
            },
            "location_values": _location_values_for_group(group),
            "sha_groups": {},
            "adjustment_metadata_profiles": {},
            "shared_fields": {},
            "differing_fields": {},
            "keep_assets": [],
            "delete_candidates": [],
            "assets": [],
        }

        if any(_asset_is_live_photo_candidate(asset) for asset in group):
            group_record["status"] = "REPORT_ONLY"
            group_record["reason"] = "LIVE_PHOTO_CANDIDATE_V1_SKIP_AUTO_DELETE"
            group_record["safety_checks"]["live_photo_candidate"] = True
            group_record["assets"] = [_summarize_asset_for_report(asset) for asset in group]

            shared_fields, differing_fields = _group_shared_and_differing_fields(group)
            group_record["shared_fields"] = shared_fields
            group_record["differing_fields"] = differing_fields

            analysis.append(group_record)
            continue

        unreadable_assets = [
            asset
            for asset in group
            if not _asset_has_readable_original(asset)
        ]

        if unreadable_assets:
            group_record["status"] = "REPORT_ONLY"
            group_record["reason"] = "UNREADABLE_ORIGINAL"
            group_record["safety_checks"]["unreadable_original"] = True
            group_record["assets"] = [_summarize_asset_for_report(asset) for asset in group]

            shared_fields, differing_fields = _group_shared_and_differing_fields(group)
            group_record["shared_fields"] = shared_fields
            group_record["differing_fields"] = differing_fields

            analysis.append(group_record)
            continue

        sha_to_assets = defaultdict(list)
        sha_errors = []

        for asset in group:
            sha256, error = _calculate_asset_sha256(asset)

            if error is not None:
                sha_errors.append(
                    {
                        "asset": _summarize_asset_for_report(asset),
                        "error": error,
                    }
                )
                continue

            sha_to_assets[sha256].append(asset)

        for sha256, sha_group in sha_to_assets.items():
            group_record["sha_groups"][sha256] = [
                _summarize_asset_for_report(asset)
                for asset in sha_group
            ]

        if sha_errors:
            group_record["status"] = "REPORT_ONLY"
            group_record["reason"] = "SHA_ERROR"
            group_record["safety_checks"]["sha_error"] = True
            group_record["sha_errors"] = sha_errors
            group_record["assets"] = [_summarize_asset_for_report(asset) for asset in group]

            shared_fields, differing_fields = _group_shared_and_differing_fields(group)
            group_record["shared_fields"] = shared_fields
            group_record["differing_fields"] = differing_fields

            analysis.append(group_record)
            continue

        if _group_has_location_conflict(group):
            group_record["status"] = "REPORT_ONLY"
            group_record["reason"] = "LOCATION_CONFLICT_V1_SKIP_AUTO_DELETE"
            group_record["safety_checks"]["location_conflict"] = True
            group_record["location_values"] = _location_values_for_group(group)
            group_record["assets"] = [_summarize_asset_for_report(asset) for asset in group]

            shared_fields, differing_fields = _group_shared_and_differing_fields(group)
            group_record["shared_fields"] = shared_fields
            group_record["differing_fields"] = differing_fields

            analysis.append(group_record)
            continue

        same_sha_groups = {
            sha256: sha_group
            for sha256, sha_group in sha_to_assets.items()
            if len(sha_group) > 1
        }

        if not same_sha_groups:
            group_record["status"] = "NOT_DUPLICATE"
            group_record["reason"] = "UNIQUE_ID_COLLISION_BUT_SHA_DIFFERS"
            group_record["assets"] = [_summarize_asset_for_report(asset) for asset in group]

            shared_fields, differing_fields = _group_shared_and_differing_fields(group)
            group_record["shared_fields"] = shared_fields
            group_record["differing_fields"] = differing_fields

            analysis.append(group_record)
            continue

        adjustment_metadata_mismatch_sha_groups = {
            sha256: sha_group
            for sha256, sha_group in same_sha_groups.items()
            if _group_has_adjustment_metadata_mismatch(sha_group)
        }

        if adjustment_metadata_mismatch_sha_groups:
            group_record["status"] = "NOT_DUPLICATE_ADJUSTED_VARIANT"
            group_record["reason"] = "SAME_UNIQUE_ID_AND_SAME_SHA256_BUT_ADJUSTMENT_METADATA_DIFFERS"
            group_record["safety_checks"]["adjustment_metadata_mismatch"] = True
            group_record["assets"] = [_summarize_asset_for_report(asset) for asset in group]

            group_record["adjustment_metadata_profiles"] = {
                sha256: [
                    repr(profile)
                    for profile in _adjustment_metadata_profiles_for_group(sha_group)
                ]
                for sha256, sha_group in adjustment_metadata_mismatch_sha_groups.items()
            }

            shared_fields, differing_fields = _group_shared_and_differing_fields(group)
            group_record["shared_fields"] = shared_fields
            group_record["differing_fields"] = differing_fields

            analysis.append(group_record)
            continue

        group_record["status"] = "DELETABLE_DUPLICATE"
        group_record["reason"] = "SAME_UNIQUE_ID_AND_SAME_SHA256_AND_SAME_ADJUSTMENT_METADATA"

        delete_candidates = []
        keep_assets = []
        all_assets_with_decision = []

        for sha256, sha_group in same_sha_groups.items():
            sorted_group = _stable_sort_assets_for_keep(sha_group)
            keep_asset = sorted_group[0]
            delete_assets = sorted_group[1:]

            for rank, asset in enumerate(sorted_group):
                asset["decision_role"] = "KEEP" if rank == 0 else "DELETE_CANDIDATE"
                asset["keep_sort_rank"] = rank
                asset["keep_decision_reason"] = _summarize_keep_decision_reason(
                    asset=asset,
                    keep_asset=keep_asset,
                )

            keep_assets.append(keep_asset)
            delete_candidates.extend(delete_assets)
            all_assets_with_decision.extend(sorted_group)

        group_record["keep_assets"] = [
            _summarize_asset_for_report(asset)
            for asset in keep_assets
        ]

        group_record["delete_candidates"] = [
            _summarize_asset_for_report(asset)
            for asset in delete_candidates
        ]

        group_record["assets"] = [
            _summarize_asset_for_report(asset)
            for asset in all_assets_with_decision
        ]

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

        shared_fields, differing_fields = _group_shared_and_differing_fields(all_assets_with_decision)
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


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _write_tsv(path, rows, fieldnames):
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


def _stringify_tsv_value(value):
    if value is None:
        return ""

    if isinstance(value, (list, tuple)):
        return " | ".join(str(item) for item in value)

    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    return str(value)


def _make_asset_report_row(group_index, record, asset, decision_role=None):
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

        "hasadjustments": asset.get("hasadjustments"),
        "adjustment_type": asset.get("adjustment_type"),
        "external_edit": asset.get("external_edit"),
        "uti_edited": asset.get("uti_edited"),
        "path_edited": asset.get("path_edited"),
        "path_edited_live_photo": asset.get("path_edited_live_photo"),
        "edited_duration_seconds": asset.get("edited_duration_seconds"),

        "has_location": bool(asset.get("location")),
        "location": asset.get("location"),
        "latitude": asset.get("latitude"),
        "longitude": asset.get("longitude"),
        "raw_location": _stringify_tsv_value(asset.get("raw_location")),
        "place": _stringify_tsv_value(asset.get("place")),

        "is_live_photo": asset.get("is_live_photo"),
        "path_live_photo": asset.get("path_live_photo"),
        "live_photo_marker": asset.get("live_photo_marker"),

        "description": asset.get("description"),
        "keywords": _stringify_tsv_value(asset.get("keywords") or []),
        "favorite": asset.get("favorite"),
        "hidden": asset.get("hidden"),
        "album_titles": _stringify_tsv_value(asset.get("album_titles") or []),
        "folder_paths": _stringify_tsv_value(asset.get("folder_paths") or []),

        "safety_checks": _stringify_tsv_value(record.get("safety_checks") or {}),
        "location_values": _stringify_tsv_value(record.get("location_values") or []),
    }


def _flatten_delete_candidate_rows(records):
    rows = []

    for group_index, record in enumerate(records, start=1):
        for asset in record.get("delete_candidates") or []:
            rows.append(
                _make_asset_report_row(
                    group_index=group_index,
                    record=record,
                    asset=asset,
                    decision_role="DELETE_CANDIDATE",
                )
            )

    return rows


def _flatten_keep_asset_rows(records):
    rows = []

    for group_index, record in enumerate(records, start=1):
        for asset in record.get("keep_assets") or []:
            rows.append(
                _make_asset_report_row(
                    group_index=group_index,
                    record=record,
                    asset=asset,
                    decision_role="KEEP",
                )
            )

    return rows


def _flatten_duplicate_review_asset_rows(records):
    rows = []

    for group_index, record in enumerate(records, start=1):
        for asset in record.get("assets") or []:
            rows.append(
                _make_asset_report_row(
                    group_index=group_index,
                    record=record,
                    asset=asset,
                    decision_role=asset.get("decision_role"),
                )
            )

    return rows


def _flatten_location_conflict_rows(records):
    rows = []

    for group_index, record in enumerate(records, start=1):
        safety_checks = record.get("safety_checks") or {}

        if not safety_checks.get("location_conflict"):
            continue

        for asset in record.get("assets") or []:
            row = _make_asset_report_row(
                group_index=group_index,
                record=record,
                asset=asset,
                decision_role=asset.get("decision_role"),
            )

            row["location_conflict_reason"] = "LOCATION_CONFLICT_V1_SKIP_AUTO_DELETE"
            row["all_location_values_in_group"] = _stringify_tsv_value(
                record.get("location_values") or []
            )

            rows.append(row)

    return rows


def _flatten_live_photo_candidate_rows(records):
    rows = []

    for group_index, record in enumerate(records, start=1):
        safety_checks = record.get("safety_checks") or {}

        if not safety_checks.get("live_photo_candidate"):
            continue

        for asset in record.get("assets") or []:
            row = _make_asset_report_row(
                group_index=group_index,
                record=record,
                asset=asset,
                decision_role=asset.get("decision_role"),
            )

            row["live_photo_reason"] = "LIVE_PHOTO_CANDIDATE_V1_SKIP_AUTO_DELETE"

            rows.append(row)

    return rows


def _flatten_assets_without_unique_id_rows(assets_without_unique_id):
    rows = []

    for asset in assets_without_unique_id:
        summarized_asset = _summarize_asset_for_report(asset)

        missing_reasons = []

        if asset.get("original_filename") is None:
            missing_reasons.append("missing original_filename")

        if _format_no_year_taipei_datetime(asset.get("date")) is None:
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
            "hasadjustments": summarized_asset.get("hasadjustments"),
            "adjustment_type": summarized_asset.get("adjustment_type"),
            "external_edit": summarized_asset.get("external_edit"),
            "uti_edited": summarized_asset.get("uti_edited"),
            "path_edited": summarized_asset.get("path_edited"),
            "path_edited_live_photo": summarized_asset.get("path_edited_live_photo"),
            "edited_duration_seconds": summarized_asset.get("edited_duration_seconds"),

            "missing_reason": " | ".join(missing_reasons),

            "has_location": bool(summarized_asset.get("location")),
            "location": summarized_asset.get("location"),
            "latitude": summarized_asset.get("latitude"),
            "longitude": summarized_asset.get("longitude"),
            "raw_location": _stringify_tsv_value(summarized_asset.get("raw_location")),
            "place": _stringify_tsv_value(summarized_asset.get("place")),

            "is_live_photo": summarized_asset.get("is_live_photo"),
            "path_live_photo": summarized_asset.get("path_live_photo"),
            "live_photo_marker": summarized_asset.get("live_photo_marker"),

            "description": summarized_asset.get("description"),
            "keywords": _stringify_tsv_value(summarized_asset.get("keywords") or []),
            "favorite": summarized_asset.get("favorite"),
            "hidden": summarized_asset.get("hidden"),
            "album_titles": _stringify_tsv_value(summarized_asset.get("album_titles") or []),
            "folder_paths": _stringify_tsv_value(summarized_asset.get("folder_paths") or []),
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

    "hasadjustments",
    "adjustment_type",
    "external_edit",
    "uti_edited",
    "path_edited",
    "path_edited_live_photo",
    "edited_duration_seconds",

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
    "hasadjustments",
    "adjustment_type",
    "external_edit",
    "uti_edited",
    "path_edited",
    "path_edited_live_photo",
    "edited_duration_seconds",

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
    delete_candidate_rows = _flatten_delete_candidate_rows(duplicate_analysis)
    keep_asset_rows = _flatten_keep_asset_rows(duplicate_analysis)
    duplicate_review_asset_rows = _flatten_duplicate_review_asset_rows(duplicate_analysis)
    location_conflict_rows = _flatten_location_conflict_rows(duplicate_analysis)
    live_photo_candidate_rows = _flatten_live_photo_candidate_rows(duplicate_analysis)
    assets_without_unique_id_rows = _flatten_assets_without_unique_id_rows(assets_without_unique_id)

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

    _write_json(report_dir / "duplicate_analysis.json", duplicate_analysis)
    _write_json(report_dir / "kept_assets.json", keep_asset_rows)
    _write_json(report_dir / "delete_candidates.json", delete_candidate_rows)
    _write_json(report_dir / "duplicate_review_assets.json", duplicate_review_asset_rows)
    _write_json(report_dir / "assets_without_unique_id.json", assets_without_unique_id_rows)

    _write_tsv(
        report_dir / "duplicate_review_assets.tsv",
        duplicate_review_asset_rows,
        DUPLICATE_REVIEW_TSV_FIELDS,
    )

    _write_tsv(
        report_dir / "delete_candidates.tsv",
        delete_candidate_rows,
        DUPLICATE_REVIEW_TSV_FIELDS,
    )

    _write_tsv(
        report_dir / "kept_assets.tsv",
        keep_asset_rows,
        DUPLICATE_REVIEW_TSV_FIELDS,
    )

    _write_tsv(
        report_dir / "location_conflicts.tsv",
        location_conflict_rows,
        DUPLICATE_REVIEW_TSV_FIELDS + [
            "location_conflict_reason",
            "all_location_values_in_group",
        ],
    )

    _write_tsv(
        report_dir / "live_photo_candidates.tsv",
        live_photo_candidate_rows,
        DUPLICATE_REVIEW_TSV_FIELDS + [
            "live_photo_reason",
        ],
    )

    _write_tsv(
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


# ------------------------------------------------------------
# Cross-library comparison helpers
# ------------------------------------------------------------

class _ChangeType(str, Enum):
    ASSET_MISSING_FROM_CURRENT = "ASSET_MISSING_FROM_CURRENT"
    ASSET_PRESENT_IN_CURRENT_AS_SYNDICATED = "ASSET_PRESENT_IN_CURRENT_AS_SYNDICATED"
    ASSET_NEW_IN_CURRENT = "ASSET_NEW_IN_CURRENT"
    ASSET_METADATA_CHANGED = "ASSET_METADATA_CHANGED"
    ASSET_ALBUM_MEMBERSHIP_CHANGED = "ASSET_ALBUM_MEMBERSHIP_CHANGED"
    ASSET_FOLDER_PATHS_CHANGED = "ASSET_FOLDER_PATHS_CHANGED"
    ALBUM_MISSING_FROM_CURRENT = "ALBUM_MISSING_FROM_CURRENT"
    ALBUM_NEW_IN_CURRENT = "ALBUM_NEW_IN_CURRENT"
    ALBUM_FOLDER_PATHS_CHANGED = "ALBUM_FOLDER_PATHS_CHANGED"
    FOLDER_MISSING_FROM_CURRENT = "FOLDER_MISSING_FROM_CURRENT"
    FOLDER_NEW_IN_CURRENT = "FOLDER_NEW_IN_CURRENT"


_CHANGE_TYPE_DESCRIPTIONS = {
    _ChangeType.ASSET_MISSING_FROM_CURRENT:
        "Asset exists in backup normal assets, and no matching current normal asset or current syndicated asset was found.",
    _ChangeType.ASSET_PRESENT_IN_CURRENT_AS_SYNDICATED:
        "Asset exists in backup normal assets, and exists in current special_assets/SYNDICATED. This is not true current-missing.",
    _ChangeType.ASSET_NEW_IN_CURRENT:
        "Asset exists in current normal assets but not in backup normal assets. Usually normal because current library is later.",
    _ChangeType.ASSET_METADATA_CHANGED:
        "Same asset identity exists in both libraries, but metadata differs.",
    _ChangeType.ASSET_ALBUM_MEMBERSHIP_CHANGED:
        "Same asset identity exists in both libraries, but album membership differs.",
    _ChangeType.ASSET_FOLDER_PATHS_CHANGED:
        "Same asset identity exists in both libraries, but folder paths differ.",
    _ChangeType.ALBUM_MISSING_FROM_CURRENT:
        "Album title exists in backup but not in current.",
    _ChangeType.ALBUM_NEW_IN_CURRENT:
        "Album title exists in current but not in backup.",
    _ChangeType.ALBUM_FOLDER_PATHS_CHANGED:
        "Album title exists in both libraries, but the album folder path differs.",
    _ChangeType.FOLDER_MISSING_FROM_CURRENT:
        "Folder path exists in backup but not in current.",
    _ChangeType.FOLDER_NEW_IN_CURRENT:
        "Folder path exists in current but not in backup.",
}


def _change_type_value(change_type):
    if isinstance(change_type, _ChangeType):
        return change_type.value
    return str(change_type)


def _change_type_description(change_type):
    if not isinstance(change_type, _ChangeType):
        try:
            change_type = _ChangeType(change_type)
        except ValueError:
            return ""
    return _CHANGE_TYPE_DESCRIPTIONS.get(change_type, "")


def _add_diff(diff_records, change_type, scope, backup_object=None, current_object=None,
              backup_value=None, current_value=None, note=None):
    diff_records.append({
        "change_type": _change_type_value(change_type),
        "scope": scope,
        "backup_object": backup_object,
        "current_object": current_object,
        "backup_value": backup_value,
        "current_value": current_value,
        "description": _change_type_description(change_type),
        "note": note,
    })


def _sort_asset_ids(asset_ids):
    return sorted(asset_ids, key=repr)


def _asset_display_name(asset):
    if asset is None:
        return None
    return {
        "uuid": asset.get("uuid"),
        "original_filename": asset.get("original_filename"),
        "filename": asset.get("filename"),
        "date": asset.get("date"),
        "photo_library_asset_unique_id": asset.get("photo_library_asset_unique_id"),
    }


def _album_display_name(album):
    if album is None:
        return None
    return {
        "uuid": album.get("uuid"),
        "title": album.get("title"),
        "folder_paths": _album_folder_paths(album),
    }


def _folder_display_name(folder):
    if folder is None:
        return None
    return {
        "uuid": folder.get("uuid"),
        "title": folder.get("title"),
        "path": folder.get("path"),
    }


def _normalize_compare_scalar_value(value):
    if value is None:
        return None
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, tuple):
        return tuple(value)
    if isinstance(value, dict):
        return repr(value)
    return value


def _normalize_compare_string_tuple(values):
    if not values:
        return tuple()
    normalized = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            normalized.append(text)
    return tuple(sorted(set(normalized)))


def _compare_asset_album_titles(asset):
    albums = asset.get("albums") or {}
    return _normalize_compare_string_tuple(
        album.get("title")
        for album in albums.values()
        if album.get("title")
    )


def _album_folder_paths(album):
    # Return folder paths for one album.
    folders = album.get("folders") or {}
    return sorted(
        folder.get("path") or folder.get("title")
        for folder in folders.values()
        if folder.get("path") or folder.get("title")
    )


def _make_asset_index_for_compare(inventory):
    index = {}
    for asset in inventory.get("assets") or []:
        unique_id = asset.get("photo_library_asset_unique_id")
        if unique_id is None:
            raise RuntimeError("Normal asset has no photo_library_asset_unique_id:\n" f"{asset}")
        if unique_id in index:
            raise RuntimeError("Duplicate photo_library_asset_unique_id while making asset index:\n" f"{unique_id}")
        index[unique_id] = asset
    return index


def _make_asset_key4_for_special_lookup(asset):
    unique_id = asset.get("photo_library_asset_unique_id")
    if unique_id is not None:
        return tuple(unique_id[:4])

    file_size = _get_file_size_from_asset(asset)
    adjustment_signature = _make_adjustment_signature(asset)

    unique_id = _make_photo_library_asset_unique_id(
        original_filename=asset.get("original_filename"),
        filename=asset.get("filename"),
        date=asset.get("date"),
        file_size=file_size,
        adjustment_signature=adjustment_signature,
        sha256=None,
    )
    if unique_id is None:
        return None
    return tuple(unique_id[:4])


def _make_special_asset_key4_index(inventory, bucket_names=("SYNDICATED",)):
    index = {}
    special_assets = inventory.get("special_assets") or {}
    for bucket_name in bucket_names:
        for asset in special_assets.get(bucket_name, []):
            key4 = _make_asset_key4_for_special_lookup(asset)
            if key4 is None:
                continue
            index.setdefault(key4, []).append(asset)
    return index


def _make_album_title_index(inventory):
    index = {}
    for album in (inventory.get("albums") or {}).values():
        title = album.get("title")
        if title is None:
            continue
        index.setdefault(title, []).append(album)
    return index


def _make_folder_path_index(inventory):
    index = {}
    for folder in (inventory.get("folders") or {}).values():
        path = folder.get("path") or folder.get("title")
        if path is None:
            continue
        index.setdefault(path, []).append(folder)
    return index


def _compare_asset_existence(inventory_backup, inventory_current, diff_records):
    backup_assets = _make_asset_index_for_compare(inventory_backup)
    current_assets = _make_asset_index_for_compare(inventory_current)
    current_syndicated_by_key4 = _make_special_asset_key4_index(
        inventory_current,
        bucket_names=("SYNDICATED",),
    )
    backup_ids = set(backup_assets)
    current_ids = set(current_assets)

    for asset_id in _sort_asset_ids(backup_ids - current_ids):
        backup_asset = backup_assets[asset_id]
        asset_key4 = tuple(asset_id[:4])
        current_syndicated_matches = current_syndicated_by_key4.get(asset_key4, [])
        if current_syndicated_matches:
            _add_diff(
                diff_records=diff_records,
                change_type=_ChangeType.ASSET_PRESENT_IN_CURRENT_AS_SYNDICATED,
                scope="asset",
                backup_object=backup_asset,
                current_object=current_syndicated_matches,
                backup_value=_asset_display_name(backup_asset),
                current_value=[_asset_display_name(current_asset) for current_asset in current_syndicated_matches],
                note=(
                    "Backup normal asset is not present in current normal assets, "
                    "but a matching current special_assets/SYNDICATED asset exists by "
                    "original_filename/date/file_size/adjustment_signature. "
                    "Do not treat as true current-missing."
                ),
            )
            continue

        _add_diff(
            diff_records=diff_records,
            change_type=_ChangeType.ASSET_MISSING_FROM_CURRENT,
            scope="asset",
            backup_object=backup_asset,
            current_object=None,
            backup_value=_asset_display_name(backup_asset),
            current_value=None,
            note="Asset exists in backup normal assets, and no matching current normal asset or current syndicated asset was found.",
        )

    for asset_id in _sort_asset_ids(current_ids - backup_ids):
        current_asset = current_assets[asset_id]
        _add_diff(
            diff_records=diff_records,
            change_type=_ChangeType.ASSET_NEW_IN_CURRENT,
            scope="asset",
            backup_object=None,
            current_object=current_asset,
            backup_value=None,
            current_value=_asset_display_name(current_asset),
            note="Asset exists in current normal assets but not in backup normal assets.",
        )


def _compare_asset_metadata(inventory_backup, inventory_current, diff_records):
    backup_assets = _make_asset_index_for_compare(inventory_backup)
    current_assets = _make_asset_index_for_compare(inventory_current)
    common_ids = set(backup_assets) & set(current_assets)
    metadata_fields = ["description", "keywords", "favorite", "hidden"]

    for asset_id in _sort_asset_ids(common_ids):
        backup_asset = backup_assets[asset_id]
        current_asset = current_assets[asset_id]
        changed_fields = {}

        for field_name in metadata_fields:
            backup_value = _normalize_compare_scalar_value(backup_asset.get(field_name))
            current_value = _normalize_compare_scalar_value(current_asset.get(field_name))
            if backup_value == current_value:
                continue
            changed_fields[field_name] = {"backup": backup_value, "current": current_value}

        if not changed_fields:
            continue

        _add_diff(
            diff_records=diff_records,
            change_type=_ChangeType.ASSET_METADATA_CHANGED,
            scope="asset",
            backup_object=backup_asset,
            current_object=current_asset,
            backup_value=changed_fields,
            current_value=changed_fields,
            note="Same normal asset identity exists in both libraries, but metadata differs.",
        )


def _compare_asset_album_membership(inventory_backup, inventory_current, diff_records):
    backup_assets = _make_asset_index_for_compare(inventory_backup)
    current_assets = _make_asset_index_for_compare(inventory_current)
    common_ids = set(backup_assets) & set(current_assets)

    for asset_id in _sort_asset_ids(common_ids):
        backup_asset = backup_assets[asset_id]
        current_asset = current_assets[asset_id]
        backup_album_titles = set(_compare_asset_album_titles(backup_asset))
        current_album_titles = set(_compare_asset_album_titles(current_asset))
        if backup_album_titles == current_album_titles:
            continue

        _add_diff(
            diff_records=diff_records,
            change_type=_ChangeType.ASSET_ALBUM_MEMBERSHIP_CHANGED,
            scope="asset",
            backup_object=backup_asset,
            current_object=current_asset,
            backup_value=sorted(backup_album_titles),
            current_value=sorted(current_album_titles),
            note="Same normal asset identity exists in both libraries, but album membership differs.",
        )


def _compare_asset_folder_paths(inventory_backup, inventory_current, diff_records):
    backup_assets = _make_asset_index_for_compare(inventory_backup)
    current_assets = _make_asset_index_for_compare(inventory_current)
    common_ids = set(backup_assets) & set(current_assets)

    for asset_id in _sort_asset_ids(common_ids):
        backup_asset = backup_assets[asset_id]
        current_asset = current_assets[asset_id]
        backup_paths = set(_asset_folder_paths(backup_asset))
        current_paths = set(_asset_folder_paths(current_asset))
        if backup_paths == current_paths:
            continue

        _add_diff(
            diff_records=diff_records,
            change_type=_ChangeType.ASSET_FOLDER_PATHS_CHANGED,
            scope="asset",
            backup_object=backup_asset,
            current_object=current_asset,
            backup_value=sorted(backup_paths),
            current_value=sorted(current_paths),
            note="Same normal asset identity exists in both libraries, but folder paths differ.",
        )


def _compare_album_existence_and_folder_paths(inventory_backup, inventory_current, diff_records):
    backup_album_index = _make_album_title_index(inventory_backup)
    current_album_index = _make_album_title_index(inventory_current)
    backup_titles = set(backup_album_index)
    current_titles = set(current_album_index)

    for title in sorted(backup_titles - current_titles):
        backup_albums = backup_album_index[title]
        _add_diff(
            diff_records=diff_records,
            change_type=_ChangeType.ALBUM_MISSING_FROM_CURRENT,
            scope="album",
            backup_object=backup_albums,
            current_object=None,
            backup_value=[_album_display_name(album) for album in backup_albums],
            current_value=None,
            note="Album title exists in backup but not in current.",
        )

    for title in sorted(current_titles - backup_titles):
        current_albums = current_album_index[title]
        _add_diff(
            diff_records=diff_records,
            change_type=_ChangeType.ALBUM_NEW_IN_CURRENT,
            scope="album",
            backup_object=None,
            current_object=current_albums,
            backup_value=None,
            current_value=[_album_display_name(album) for album in current_albums],
            note="Album title exists in current but not in backup.",
        )

    for title in sorted(backup_titles & current_titles):
        backup_albums = backup_album_index[title]
        current_albums = current_album_index[title]
        if len(backup_albums) != 1 or len(current_albums) != 1:
            continue
        backup_album = backup_albums[0]
        current_album = current_albums[0]
        backup_paths = set(_album_folder_paths(backup_album))
        current_paths = set(_album_folder_paths(current_album))
        if backup_paths == current_paths:
            continue

        _add_diff(
            diff_records=diff_records,
            change_type=_ChangeType.ALBUM_FOLDER_PATHS_CHANGED,
            scope="album",
            backup_object=backup_album,
            current_object=current_album,
            backup_value=sorted(backup_paths),
            current_value=sorted(current_paths),
            note="Album title exists in both libraries, but folder path differs.",
        )


def _compare_folder_paths(inventory_backup, inventory_current, diff_records):
    backup_folder_index = _make_folder_path_index(inventory_backup)
    current_folder_index = _make_folder_path_index(inventory_current)
    backup_paths = set(backup_folder_index)
    current_paths = set(current_folder_index)

    for path in sorted(backup_paths - current_paths):
        backup_folders = backup_folder_index[path]
        _add_diff(
            diff_records=diff_records,
            change_type=_ChangeType.FOLDER_MISSING_FROM_CURRENT,
            scope="folder",
            backup_object=backup_folders,
            current_object=None,
            backup_value=[_folder_display_name(folder) for folder in backup_folders],
            current_value=None,
            note="Folder path exists in backup but not in current.",
        )

    for path in sorted(current_paths - backup_paths):
        current_folders = current_folder_index[path]
        _add_diff(
            diff_records=diff_records,
            change_type=_ChangeType.FOLDER_NEW_IN_CURRENT,
            scope="folder",
            backup_object=None,
            current_object=current_folders,
            backup_value=None,
            current_value=[_folder_display_name(folder) for folder in current_folders],
            note="Folder path exists in current but not in backup.",
        )


def compare_inventories(inventory_backup, inventory_current):
    diff_records = []
    _compare_asset_existence(inventory_backup, inventory_current, diff_records)
    _compare_asset_metadata(inventory_backup, inventory_current, diff_records)
    _compare_asset_album_membership(inventory_backup, inventory_current, diff_records)
    _compare_asset_folder_paths(inventory_backup, inventory_current, diff_records)
    _compare_album_existence_and_folder_paths(inventory_backup, inventory_current, diff_records)
    _compare_folder_paths(inventory_backup, inventory_current, diff_records)
    return diff_records


def filter_diff_records(diff_records, change_type):
    change_type = _change_type_value(change_type)
    return [record for record in diff_records if record.get("change_type") == change_type]


def summarize_diff_records(diff_records):
    print("diff record count:", len(diff_records))
    print()
    counts = Counter(record.get("change_type") for record in diff_records)
    print("change_type counts")
    print("-" * 80)
    for change_type, count in sorted(counts.items()):
        print(f"{change_type}: {count}")

    print()
    scope_counts = Counter(record.get("scope") for record in diff_records)
    print("scope counts")
    print("-" * 80)
    for scope, count in sorted(scope_counts.items()):
        print(f"{scope}: {count}")


# ------------------------------------------------------------
# ASSET_MISSING_FROM_CURRENT review report helpers
# ------------------------------------------------------------

def _format_file_size_for_review(value):
    if value is None:
        return "-"
    try:
        return f"{int(value):,} bytes"
    except Exception:
        return str(value)


def _asset_original_resolution(asset):
    original_width = asset.get("original_width")
    original_height = asset.get("original_height")
    if original_width is None or original_height is None:
        return "-"
    return f"{original_width}x{original_height}"


def _asset_current_candidate_line(asset, prefix="  current_candidate"):
    unique_id = asset.get("photo_library_asset_unique_id")
    date_key = unique_id[1] if unique_id and len(unique_id) > 1 else "-"
    file_size = unique_id[2] if unique_id and len(unique_id) > 2 else _get_file_size_from_asset(asset)
    adjustment_signature = unique_id[3] if unique_id and len(unique_id) > 3 else _make_adjustment_signature(asset)
    path = asset.get("path")
    scope = asset.get("local_file_status") or "NORMAL"

    return (
        f"{prefix}: "
        f"{scope} | "
        f"uuid={asset.get('uuid')} | "
        f"date_key={date_key} | "
        f"file_size={_format_file_size_for_review(file_size)} | "
        f"adjustment_signature={adjustment_signature} | "
        f"original_size={_asset_original_resolution(asset)} | "
        f"hasadjustments={asset.get('hasadjustments')} | "
        f"path_exists={None if path is None else os.path.exists(path)}"
    )


def _build_current_filename_candidate_index(inventory_current):
    index = defaultdict(list)
    for asset in inventory_current.get("assets") or []:
        filename = asset.get("original_filename") or asset.get("filename")
        if filename:
            index[filename].append(asset)

    for bucket_name, assets in (inventory_current.get("special_assets") or {}).items():
        for asset in assets:
            filename = asset.get("original_filename") or asset.get("filename")
            if filename:
                candidate = dict(asset)
                candidate["local_file_status"] = bucket_name
                index[filename].append(candidate)
    return index


def _missing_current_review_rows(missing_records, inventory_current):
    current_filename_index = _build_current_filename_candidate_index(inventory_current)
    rows = []

    for index, record in enumerate(missing_records, start=1):
        asset = record.get("backup_object") or {}
        path = asset.get("path")
        unique_id = asset.get("photo_library_asset_unique_id")
        original_filename = asset.get("original_filename") or asset.get("filename")
        current_candidates = current_filename_index.get(original_filename, [])

        row = {
            "index": index,
            "change_type": record.get("change_type"),
            "description": record.get("description"),
            "note": record.get("note"),
            "uuid": asset.get("uuid"),
            "original_filename": original_filename,
            "unique_id_repr": repr(unique_id),
            "date": asset.get("date"),
            "date_added": asset.get("date_added"),
            "date_modified": asset.get("date_modified"),
            "is_movie": asset.get("is_movie"),
            "file_size": unique_id[2] if unique_id and len(unique_id) > 2 else _get_file_size_from_asset(asset),
            "original_resolution": _asset_original_resolution(asset),
            "hasadjustments": asset.get("hasadjustments"),
            "adjustment_signature": unique_id[3] if unique_id and len(unique_id) > 3 else _make_adjustment_signature(asset),
            "path_exists": None if path is None else os.path.exists(path),
            "path": path,
            "path_edited": asset.get("path_edited"),
            "description_text": asset.get("description") or "-",
            "keywords": list(asset.get("keywords") or []),
            "favorite": asset.get("favorite"),
            "hidden": asset.get("hidden"),
            "first_album": (list(_compare_asset_album_titles(asset)) or ["-"])[0],
            "all_albums": list(_compare_asset_album_titles(asset)),
            "folders": list(_asset_folder_paths(asset)),
            "current_candidate_count_same_original_filename": len(current_candidates),
            "current_candidates": current_candidates,
        }
        rows.append(row)

    return rows


def _write_missing_review_txt(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        f.write("=" * 120 + "\n")
        f.write("Section 5A: Compact ASSET_MISSING_FROM_CURRENT review list\n")
        f.write("=" * 120 + "\n")
        f.write(f"matched record count: {len(rows)}\n\n")

        f.write("Quick counts\n")
        f.write("-" * 120 + "\n")
        f.write(f"is_movie: {dict(Counter(row.get('is_movie') for row in rows))}\n")
        f.write(f"hasadjustments: {dict(Counter(row.get('hasadjustments') for row in rows))}\n")
        f.write(f"favorite: {dict(Counter(row.get('favorite') for row in rows))}\n")
        f.write(f"hidden: {dict(Counter(row.get('hidden') for row in rows))}\n")
        f.write(f"path_exists: {dict(Counter(row.get('path_exists') for row in rows))}\n\n")

        f.write("=" * 120 + "\n")
        f.write("One-by-one manual verification checklist\n")
        f.write("=" * 120 + "\n\n")

        for row in rows:
            f.write(f"{row['index']:02d}. {row.get('original_filename')}\n")
            f.write("-" * 120 + "\n")
            f.write(f"change_type: {row.get('change_type')}\n")
            f.write(f"description: {row.get('description')}\n")
            f.write(f"note: {row.get('note')}\n")
            f.write(f"uuid: {row.get('uuid')}\n")
            f.write(f"unique_id: {row.get('unique_id_repr')}\n")
            f.write(f"date: {row.get('date')}\n")
            f.write(f"date_added: {row.get('date_added')}\n")
            f.write(f"date_modified: {row.get('date_modified')}\n")
            f.write(f"file_size: {_format_file_size_for_review(row.get('file_size'))}\n")
            f.write(f"original_size: {row.get('original_resolution')}\n")
            f.write(f"hasadjustments: {row.get('hasadjustments')}\n")
            f.write(f"adjustment_signature: {row.get('adjustment_signature')}\n")
            f.write(f"path_exists: {row.get('path_exists')}\n")
            f.write(f"path: {row.get('path')}\n")
            f.write(f"path_edited: {row.get('path_edited')}\n")
            f.write(f"description_text: {row.get('description_text')}\n")
            f.write(f"keywords: {row.get('keywords')}\n")
            f.write(f"favorite: {row.get('favorite')}\n")
            f.write(f"hidden: {row.get('hidden')}\n")
            f.write(f"first_album: {row.get('first_album')}\n")
            f.write(f"all_albums: {row.get('all_albums')}\n")
            f.write(f"folders: {row.get('folders')}\n")
            f.write("current candidates with same original_filename: "
                    f"{row.get('current_candidate_count_same_original_filename')}\n")

            for candidate_index, candidate in enumerate(row.get("current_candidates") or [], start=1):
                if candidate_index > 5:
                    f.write("  ... more current candidates not printed\n")
                    break
                f.write(_asset_current_candidate_line(candidate, prefix=f"  current_candidate_{candidate_index}") + "\n")
            f.write("\n")


def _write_missing_review_tsv(path, rows):
    fieldnames = [
        "index", "change_type", "uuid", "original_filename", "date", "date_added",
        "date_modified", "is_movie", "file_size", "original_resolution", "hasadjustments",
        "adjustment_signature", "path_exists", "path", "path_edited", "description_text",
        "keywords", "favorite", "hidden", "first_album", "all_albums", "folders",
        "current_candidate_count_same_original_filename",
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _stringify_tsv_value(row.get(key)) for key in fieldnames})



def _print_missing_review_rows(rows, max_current_candidates=5):
    print("=" * 120)
    print("Section 5A: Compact ASSET_MISSING_FROM_CURRENT review list")
    print("=" * 120)
    print(f"matched record count: {len(rows)}")
    print()

    print("Quick counts")
    print("-" * 120)
    print(f"is_movie: {dict(Counter(row.get('is_movie') for row in rows))}")
    print(f"hasadjustments: {dict(Counter(row.get('hasadjustments') for row in rows))}")
    print(f"favorite: {dict(Counter(row.get('favorite') for row in rows))}")
    print(f"hidden: {dict(Counter(row.get('hidden') for row in rows))}")
    print(f"path_exists: {dict(Counter(row.get('path_exists') for row in rows))}")
    print()

    print("=" * 120)
    print("One-by-one manual verification checklist")
    print("=" * 120)
    print()

    for row in rows:
        print(f"{row['index']:02d}. {row.get('original_filename')}")
        print("-" * 120)
        print(f"change_type: {row.get('change_type')}")
        print(f"description: {row.get('description')}")
        print(f"note: {row.get('note')}")
        print(f"uuid: {row.get('uuid')}")
        print(f"unique_id: {row.get('unique_id_repr')}")
        print(f"date: {row.get('date')}")
        print(f"date_added: {row.get('date_added')}")
        print(f"date_modified: {row.get('date_modified')}")
        print(f"file_size: {_format_file_size_for_review(row.get('file_size'))}")
        print(f"original_size: {row.get('original_resolution')}")
        print(f"hasadjustments: {row.get('hasadjustments')}")
        print(f"adjustment_signature: {row.get('adjustment_signature')}")
        print(f"path_exists: {row.get('path_exists')}")
        print(f"path: {row.get('path')}")
        print(f"path_edited: {row.get('path_edited')}")
        print(f"description_text: {row.get('description_text')}")
        print(f"keywords: {row.get('keywords')}")
        print(f"favorite: {row.get('favorite')}")
        print(f"hidden: {row.get('hidden')}")
        print(f"first_album: {row.get('first_album')}")
        print(f"all_albums: {row.get('all_albums')}")
        print(f"folders: {row.get('folders')}")
        print(
            "current candidates with same original_filename: "
            f"{row.get('current_candidate_count_same_original_filename')}"
        )

        for candidate_index, candidate in enumerate(row.get("current_candidates") or [], start=1):
            if candidate_index > max_current_candidates:
                print("  ... more current candidates not printed")
                break
            print(
                _asset_current_candidate_line(
                    candidate,
                    prefix=f"  current_candidate_{candidate_index}",
                )
            )
        print()


def print_missing_current_review(
    diff_records,
    inventory_current,
    max_current_candidates=5,
):
    missing_records = filter_diff_records(diff_records, _ChangeType.ASSET_MISSING_FROM_CURRENT)
    rows = _missing_current_review_rows(
        missing_records=missing_records,
        inventory_current=inventory_current,
    )

    _print_missing_review_rows(
        rows=rows,
        max_current_candidates=max_current_candidates,
    )

    return {
        "matched_record_count": len(rows),
        "rows": rows,
    }


def write_missing_current_review_report(
    diff_records,
    inventory_current,
    output_dir,
    report_name_prefix="asset_missing_from_current_review",
):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    missing_records = filter_diff_records(diff_records, _ChangeType.ASSET_MISSING_FROM_CURRENT)
    rows = _missing_current_review_rows(missing_records=missing_records, inventory_current=inventory_current)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_path = output_dir / f"{report_name_prefix}_{timestamp}.txt"
    tsv_path = output_dir / f"{report_name_prefix}_{timestamp}.tsv"

    _write_missing_review_txt(txt_path, rows)
    _write_missing_review_tsv(tsv_path, rows)

    return {
        "matched_record_count": len(rows),
        "text_report_path": txt_path,
        "tsv_report_path": tsv_path,
        "rows": rows,
    }


def print_missing_current_review_report_summary(result):
    print("ASSET_MISSING_FROM_CURRENT review")
    print("-" * 80)
    print("matched record count:", result.get("matched_record_count"))
    print("text report:", result.get("text_report_path"))
    print("tsv report:", result.get("tsv_report_path"))

