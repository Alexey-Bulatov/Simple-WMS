from __future__ import annotations

import fcntl
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import get_settings


def required_binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"Required executable is not installed: {name}")
    return path


def main() -> None:
    url = make_url(get_settings().database_url)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("Automated backup supports PostgreSQL only")
    if not url.database:
        raise RuntimeError("DATABASE_URL has no database name")

    backup_dir = Path(os.getenv("WMS_BACKUP_DIR", "/var/backups/simple-wms"))
    retention_days = int(os.getenv("WMS_BACKUP_RETENTION_DAYS", "14"))
    if retention_days < 1:
        raise RuntimeError("WMS_BACKUP_RETENTION_DAYS must be positive")
    backup_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    filename = f"simple-wms-{now:%Y%m%dT%H%M%SZ}.dump"
    final_path = backup_dir / filename
    temporary_path = backup_dir / f".{filename}.tmp"
    lock_path = backup_dir / ".backup.lock"

    environment = os.environ.copy()
    if url.password:
        environment["PGPASSWORD"] = url.password

    pg_dump = required_binary("pg_dump")
    pg_restore = required_binary("pg_restore")
    command = [pg_dump, "--format=custom", "--file", str(temporary_path)]
    if url.host:
        command.extend(["--host", url.host])
    if url.port:
        command.extend(["--port", str(url.port)])
    if url.username:
        command.extend(["--username", url.username])
    command.append(url.database)

    with lock_path.open("w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            subprocess.run(command, check=True, env=environment)
            subprocess.run(
                [pg_restore, "--list", str(temporary_path)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            os.replace(temporary_path, final_path)
            final_path.chmod(0o600)
        finally:
            temporary_path.unlink(missing_ok=True)

        cutoff = now - timedelta(days=retention_days)
        removed = 0
        for old_backup in backup_dir.glob("simple-wms-*.dump"):
            if datetime.fromtimestamp(old_backup.stat().st_mtime, timezone.utc) < cutoff:
                old_backup.unlink()
                removed += 1

    print(f"Backup verified: {final_path} ({final_path.stat().st_size} bytes); removed: {removed}")


if __name__ == "__main__":
    main()
