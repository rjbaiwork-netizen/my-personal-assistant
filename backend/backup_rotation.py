from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/app/storage")).resolve()
BACKUP_DIR = STORAGE_DIR / "backups"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _retention_count() -> int:
    try:
        return max(1, int(os.getenv("BACKUP_RETENTION_COUNT", "7")))
    except ValueError:
        return 7


def create_rotated_backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_base = BACKUP_DIR / f"system_backup_{stamp}"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "my-personal-assistant"
        root.mkdir()

        for item in PROJECT_ROOT.iterdir():
            if item.name in {".git", "storage"} or item.name.startswith("."):
                continue
            destination = root / item.name
            if item.is_dir():
                shutil.copytree(item, destination)
            else:
                shutil.copy2(item, destination)

        storage_copy = root / "storage"
        storage_copy.mkdir()
        for item in STORAGE_DIR.iterdir():
            if item.name == "backups":
                continue
            destination = storage_copy / item.name
            if item.name == "config.json":
                import json
                try:
                    config = json.loads(item.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    config = {}
                config["gemini_api_key"] = ""
                destination.write_text(
                    json.dumps(config, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            elif item.is_dir():
                shutil.copytree(item, destination)
            else:
                shutil.copy2(item, destination)

        archive = Path(
            shutil.make_archive(
                str(archive_base), "zip", root_dir=tmp, base_dir=root.name
            )
        )

    _rotate_local_backups()
    return archive


def _rotate_local_backups() -> None:
    backups = sorted(
        BACKUP_DIR.glob("system_backup_*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in backups[_retention_count():]:
        try:
            path.unlink()
        except OSError:
            pass


def sync_excel_to_s3() -> list[str]:
    bucket = os.getenv("BACKUP_S3_BUCKET", "").strip()
    if not bucket:
        return []
    import boto3
    prefix = os.getenv("BACKUP_S3_PREFIX", "my-personal-assistant").strip("/")
    client = boto3.client("s3", region_name=os.getenv("AWS_REGION") or None, endpoint_url=os.getenv("BACKUP_S3_ENDPOINT") or None)
    uploaded = []
    excel_dir = STORAGE_DIR / "excel_files"
    for path in excel_dir.glob("*.xlsx"):
        key = f"{prefix}/excel/{path.name}" if prefix else f"excel/{path.name}"
        client.upload_file(str(path), bucket, key, ExtraArgs={"ServerSideEncryption": "AES256"})
        uploaded.append(f"s3://{bucket}/{key}")
    return uploaded


def cleanup_remote_backups() -> int:
    bucket = os.getenv("BACKUP_S3_BUCKET", "").strip()
    if not bucket:
        return 0
    import boto3
    prefix = os.getenv("BACKUP_S3_PREFIX", "my-personal-assistant").strip("/") + "/"
    client = boto3.client("s3", region_name=os.getenv("AWS_REGION") or None, endpoint_url=os.getenv("BACKUP_S3_ENDPOINT") or None)
    response = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    objects = [o for o in response.get("Contents", []) if "/excel/" not in o["Key"] and o["Key"].endswith(".zip")]
    objects.sort(key=lambda o: o["LastModified"], reverse=True)
    deleted = 0
    for obj in objects[_retention_count():]:
        client.delete_object(Bucket=bucket, Key=obj["Key"])
        deleted += 1
    return deleted


def backup_status() -> dict:
    files = sorted(
        BACKUP_DIR.glob("system_backup_*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return {
        "retention_count": _retention_count(),
        "count": len(files),
        "latest": files[0].name if files else None,
        "s3_enabled": bool(os.getenv("BACKUP_S3_BUCKET")),
    }


def upload_to_s3(path: Path) -> str | None:
    bucket = os.getenv("BACKUP_S3_BUCKET", "").strip()
    if not bucket:
        return None

    import boto3

    prefix = os.getenv("BACKUP_S3_PREFIX", "my-personal-assistant").strip("/")
    key = f"{prefix}/{path.name}" if prefix else path.name
    client = boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION") or None,
        endpoint_url=os.getenv("BACKUP_S3_ENDPOINT") or None,
    )
    client.upload_file(
        str(path),
        bucket,
        key,
        ExtraArgs={"ServerSideEncryption": "AES256"},
    )
    return f"s3://{bucket}/{key}"
