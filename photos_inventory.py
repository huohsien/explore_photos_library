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


__all__ = [
    "build_inventory",
    "print_inventory_summary",

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
    return {
        "uuid": osx_asset.uuid,

        "filename": osx_asset.filename,
        "original_filename": osx_asset.original_filename,
        "path": str(osx_asset.path) if osx_asset.path else None,

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
    inventory = {
        "assets": [],    # list[Asset object]
        "albums": {},    # album_uuid -> Album object
        "folders": {},   # folder_uuid -> Folder object
        "errors": [],
    }

    seen_asset_uuids = set()

    for index, osx_asset in enumerate(osx_assets, start=1):
        asset = _create_asset_object(osx_asset)
        asset_uuid = asset["uuid"]

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