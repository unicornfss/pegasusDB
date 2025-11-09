# unicorn_project/training/drive_paths.py

FOLDER_MIME = "application/vnd.google-apps.folder"

def _find_or_create_folder(svc, name: str, parent_id: str) -> str:
    # Escape single quotes in search string
    safe = name.replace("'", "\\'")
    q = (
        f"name = '{safe}' and mimeType = '{FOLDER_MIME}' "
        f"and '{parent_id}' in parents and trashed = false"
    )
    res = svc.files().list(q=q, fields="files(id,name)", pageSize=1).execute()
    got = res.get("files", [])
    if got:
        return got[0]["id"]
    meta = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
    return svc.files().create(body=meta, fields="id").execute()["id"]

def ensure_path(svc, segments: list[str], root_id: str) -> str:
    cur = root_id
    for seg in segments:
        cur = _find_or_create_folder(svc, seg, cur)
    return cur

# find a child folder by name under a parent (do NOT create)
def find_folder(svc, name: str, parent_id: str) -> str | None:
    FOLDER_MIME = "application/vnd.google-apps.folder"
    safe = name.replace("'", "\\'")
    q = (
        f"name = '{safe}' and mimeType = '{FOLDER_MIME}' "
        f"and '{parent_id}' in parents and trashed = false"
    )
    res = svc.files().list(q=q, fields="files(id,name)", pageSize=1).execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None
