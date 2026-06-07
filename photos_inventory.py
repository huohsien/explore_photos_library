# ============================================================
# photos_inventory.py
#
# Core helper functions for building, searching, saving, and
# loading Photos Library metadata inventories from osxphotos.
# ============================================================

import gzip
import os
import pickle
import time
from datetime import datetime
from zoneinfo import ZoneInfo


__all__ = [
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


def _get_attr(obj, name, default=None):
    # Safely get an attribute from an osxphotos object.
    if not hasattr(obj, name):
        return default

    value = getattr(obj, name)

    if callable(value):
        return value()

    return value

def _classify_asset_path_string(path):
    # Classify where an asset file lives inside a Photos Library.
    #
    # NORMAL_ORIGINALS:
    #   Regular Photos Library originals that should participate in
    #   backup-vs-current comparison.
    #
    # SCOPES_SYNDICATION:
    #   Shared-with-You / Messages syndicated items stored under
    #   Photos Library.photoslibrary/scopes/syndication/.
    #   These are visible through Photos-related UI but are not normal
    #   saved Photos Library originals, so they must not participate in
    #   the main repair comparison.
    #
    # PATH_NONE:
    #   Photos database has an asset record, but osxphotos did not provide
    #   a local file path. Keep this in assets for now; investigate later.
    #
    # UNKNOWN_PATH:
    #   Any path pattern we have not explicitly classified yet. Do not
    #   silently treat this as a normal original.
    if path is None:
        return "PATH_NONE"

    path_string = str(path)

    if "/scopes/syndication/" in path_string:
        return "SCOPES_SYNDICATION"

    if "/originals/" in path_string:
        return "NORMAL_ORIGINALS"

    return "UNKNOWN_PATH"


def classify_asset_path_scope(asset):
    # Public helper for already-built inventory asset objects.
    return _classify_asset_path_string(asset.get("path"))

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
    # Format asset capture date for matching.
    #
    # Year is removed because the user may intentionally change years
    # for Photos sorting.
    dt = _to_taipei_datetime(value)

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
    file_size_bytes,
):
    # Current proposed Photo Library asset unique ID.
    #
    # Scheme:
    #   1. full original_filename
    #   2. capture date converted to Asia/Taipei, year removed
    #   3. original file size in bytes
    #
    # date_added is intentionally excluded because repair/import operations
    # create a new date_added value.
    filename_for_id = original_filename or filename

    no_year_datetime = _format_no_year_taipei_datetime(date)

    if filename_for_id is None or no_year_datetime is None or file_size_bytes is None:
        return None

    return (
        filename_for_id,
        no_year_datetime,
        file_size_bytes,
    )


def _get_file_size_bytes_from_asset(asset):
    path = asset.get("path")

    if path is None:
        return None

    try:
        return os.path.getsize(path)
    except OSError:
        return None
    
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
    # Create one Asset object from one osxphotos asset.
    path = str(osx_asset.path) if osx_asset.path else None
    asset_scope = _classify_asset_path_string(path)

    return {
        "uuid": osx_asset.uuid,

        "filename": osx_asset.filename,
        "original_filename": osx_asset.original_filename,
        "path": path,
        "asset_scope": asset_scope,

        "is_movie": bool(osx_asset.ismovie),

        "date": _to_iso_string(osx_asset.date),
        "date_added": _to_iso_string(osx_asset.date_added),

        "description": osx_asset.description,
        "keywords": tuple(osx_asset.keywords),
        "favorite": bool(osx_asset.favorite),
        "hidden": _get_attr(osx_asset, "hidden", default=None),

        "albums": {},   # album_uuid -> Album object
        "folders": {},  # folder_uuid -> Folder object
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
    # Build inventory from osxphotos assets.
    #
    # Important boundary:
    # inventory["assets"] is the main comparison input and should only contain
    # normal Photos Library assets plus unresolved PATH_NONE records for now.
    #
    # SCOPES_SYNDICATION assets are kept separately because they are
    # Shared-with-You / Messages syndicated records, not normal saved Photos
    # Library originals. Including them in inventory["assets"] pollutes
    # unique-ID audit and backup-vs-current repair comparison.
    inventory = {
        "assets": [],          # list[Asset object] for formal comparison
        "special_assets": {
            "SCOPES_SYNDICATION": [],
        },
        "albums": {},          # album_uuid -> Album object
        "folders": {},         # folder_uuid -> Folder object
        "errors": [],
    }

    seen_asset_uuids = set()
    seen_syndication_asset_uuids = set()

    for index, osx_asset in enumerate(osx_assets, start=1):
        asset = _create_asset_object(osx_asset)
        asset_uuid = asset["uuid"]

        if asset["asset_scope"] == "SCOPES_SYNDICATION":
            if asset_uuid in seen_syndication_asset_uuids:
                raise RuntimeError(f"Duplicate syndication asset UUID: {asset_uuid}")

            seen_syndication_asset_uuids.add(asset_uuid)
            inventory["special_assets"]["SCOPES_SYNDICATION"].append(asset)

            if index % 10000 == 0:
                print("processed assets:", index)

            continue

        if asset_uuid in seen_asset_uuids:
            raise RuntimeError(f"Duplicate asset UUID: {asset_uuid}")

        seen_asset_uuids.add(asset_uuid)

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

    return inventory

# ------------------------------------------------------------
# Public inventory summary
# ------------------------------------------------------------

def print_inventory_summary(inventory):
    # Print basic inventory counts and metadata counts.
    print("inventory assets:", len(inventory["assets"]))
    print("inventory albums:", len(inventory["albums"]))
    print("inventory folders:", len(inventory["folders"]))

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
    # Fill or refresh photo_library_asset_unique_id for all assets.
    #
    # Current scheme uses:
    #   1. original_filename or filename
    #   2. capture date converted to Asia/Taipei, year removed
    #   3. original file size in bytes
    #
    # date_added is intentionally not used because repaired/imported assets
    # receive a new date_added value.
    for asset in inventory["assets"]:
        file_size_bytes = _get_file_size_bytes_from_asset(asset)

        asset["file_size_bytes"] = file_size_bytes

        asset["photo_library_asset_unique_id"] = _make_photo_library_asset_unique_id(
            original_filename=asset.get("original_filename"),
            filename=asset.get("filename"),
            date=asset.get("date"),
            file_size_bytes=file_size_bytes,
        )

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