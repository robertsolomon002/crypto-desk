"""Weekly backup of the tables nothing can rebuild (Stage 8.1, D53).

Neon Free keeps only 6 hours of restore history and one manual snapshot, with no scheduled
backups (neon.com/docs/introduction/plans, checked 2026-11-04), so `ops.yml` runs this weekly:

1. `pg_dump --format=custom --data-only` of `ops.backup.tables` over Neon's direct host (the
   client must be at least the server's major version: Neon runs Postgres 18);
2. `pg_restore --list` on the file, which must hold one TABLE DATA entry per table;
3. `gpg --symmetric` (AES256) with `BACKUP_PASSPHRASE`, passed on stdin, never in argv; the
   plain dump is deleted;
4. upload to the private bucket through the Cloud Storage JSON API with `ifGenerationMatch=0`
   (create only: the deployer has `roles/storage.objectCreator`, which can't read, overwrite
   or delete), using the access token from the workflow's Workload Identity login;
5. a `job_runs` row (`backup`) with the outcome.

The dump holds MCO-derived rows (Decision 6), so it never goes to a CI artifact or a log: the
log shows file names, sizes and counts only. Restore steps: docs/OPS.md, "Restore a backup".
"""

import datetime as dt
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from desk.deploy.migrate import direct_url
from desk.models import JobRun
from desk.ops import ops_settings

JOB = "backup"
UPLOAD = "https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"

Run = Callable[..., subprocess.CompletedProcess]


class BackupError(RuntimeError):
    """A failed step; the message never holds the database password or the passphrase."""


@dataclass
class BackupResult:
    run_id: int | None
    started: dt.datetime
    status: str = "running"
    name: str | None = None
    tables: int = 0
    dump_bytes: int = 0
    encrypted_bytes: int = 0
    uploaded: str | None = None  # gs://bucket/object
    error: str | None = None
    lines: list[str] = field(default_factory=list)

    def summary(self) -> str:
        out = [f"Backup {self.started:%Y-%m-%d %H:%M} UTC: {self.status}"]
        if self.name:
            out.append(f"- file {self.name}: {self.tables} tables, dump {self.dump_bytes:,} B, "
                       f"encrypted {self.encrypted_bytes:,} B")  # fmt: skip
        if self.uploaded:
            out.append(f"- uploaded to {self.uploaded}")
        if self.error:
            out.append(f"- error: {self.error}")
        return "\n".join(out)


def libpq_url(url: str) -> str:
    """The direct-host URL in libpq form (`postgresql://`, no SQLAlchemy driver)."""
    return make_url(direct_url(url)).set(drivername="postgresql").render_as_string(
        hide_password=False)  # fmt: skip


def _scrub(text: str, *secrets: str | None) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "[redacted]")
    return text.strip()[-500:]


def _call(run: Run, args: list[str], what: str, secrets: tuple[str | None, ...],
          stdin: bytes | None = None,
          env: dict[str, str] | None = None) -> subprocess.CompletedProcess:  # fmt: skip
    try:
        proc = run(args, input=stdin, capture_output=True, check=False, env=env)
    except FileNotFoundError:
        raise BackupError(f"{what}: {args[0]} is not installed") from None
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace") if isinstance(proc.stderr, bytes) else (
            proc.stderr or "")  # fmt: skip
        raise BackupError(f"{what} exited {proc.returncode}: {_scrub(err, *secrets)}")
    return proc


def dump(url: str, tables: list[str], out: Path, run: Run = subprocess.run) -> int:
    """pg_dump the tables' data into `out`; returns the number of TABLE DATA entries."""
    parsed = make_url(libpq_url(url))
    password = parsed.password
    # The password travels in PGPASSWORD, so it is not in the process list.
    # (`URL.set(password=None)` means "unchanged" in SQLAlchemy, so the tuple field is replaced.)
    target = parsed._replace(password=None).render_as_string(hide_password=False)
    env = {**os.environ, **({"PGPASSWORD": str(password)} if password else {})}
    args = ["pg_dump", "--format=custom", "--compress=6", "--data-only", "--no-owner",
            "--no-privileges", *[f"--table=public.{t}" for t in tables],
            f"--file={out}", f"--dbname={target}"]  # fmt: skip
    _call(run, args, "pg_dump", (str(password) if password else None,), env=env)
    listing = _call(run, ["pg_restore", "--list", str(out)], "pg_restore --list", ())
    text = listing.stdout.decode("utf-8", "replace") if isinstance(listing.stdout, bytes) else (
        listing.stdout or "")  # fmt: skip
    found = sum(1 for line in text.splitlines() if " TABLE DATA public " in line)
    if found != len(tables):
        raise BackupError(f"the dump holds {found} tables, expected {len(tables)}")
    return found


def encrypt(src: Path, out: Path, passphrase: str, run: Run = subprocess.run) -> None:
    args = ["gpg", "--batch", "--yes", "--pinentry-mode", "loopback", "--passphrase-fd", "0",
            "--symmetric", "--cipher-algo", "AES256", "--output", str(out), str(src)]  # fmt: skip
    _call(run, args, "gpg", (passphrase,), stdin=passphrase.encode("utf-8"))


def upload(path: Path, bucket: str, name: str, token: str,
           client: httpx.Client | None = None) -> str:  # fmt: skip
    """Create `name` in the bucket (refused if it already exists); returns its gs:// URL."""
    own = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(120.0))
    try:
        resp = client.post(
            UPLOAD.format(bucket=quote(bucket, safe="")),
            params={"uploadType": "media", "name": name, "ifGenerationMatch": "0"},
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/octet-stream"},
            content=path.read_bytes(),
        )  # fmt: skip
    except httpx.HTTPError as exc:
        raise BackupError(f"upload: {type(exc).__name__}") from None
    finally:
        if own:
            client.close()
    if resp.status_code == 412:
        raise BackupError(f"upload: gs://{bucket}/{name} already exists")
    if not resp.is_success:
        raise BackupError(f"upload: HTTP {resp.status_code}")
    return f"gs://{bucket}/{name}"


def run_backup(
    sessions: sessionmaker[Session],
    url: str,
    workdir: Path,
    passphrase: str | None,
    token: str | None,
    now: dt.datetime | None = None,
    run: Run = subprocess.run,
    client: httpx.Client | None = None,
    record: bool = True,
) -> BackupResult:
    """Dump, check, encrypt and upload. `token=None` keeps the encrypted file in `workdir`
    (a local run); the plain dump is always deleted."""
    cfg = ops_settings().get("backup") or {}
    now = now or dt.datetime.now(dt.UTC)
    result = BackupResult(run_id=None, started=now)
    if record:
        with sessions.begin() as s:
            row = JobRun(job=JOB, started_at=now)
            s.add(row)
            s.flush()
            result.run_id = row.id
    tables = list(cfg.get("tables") or [])
    with sessions() as s:  # restore into a database migrated to this revision first
        revision = s.scalar(text("SELECT version_num FROM alembic_version")) or "none"
    plain = workdir / f"desk-{now:%Y-%m-%d}-r{revision}.dump"
    sealed = plain.with_name(plain.name + ".gpg")
    result.name = sealed.name
    try:
        if not passphrase:
            raise BackupError("BACKUP_PASSPHRASE is not set")
        if not tables:
            raise BackupError("ops.backup.tables is empty")
        result.tables = dump(url, tables, plain, run)
        result.dump_bytes = plain.stat().st_size
        encrypt(plain, sealed, passphrase, run)
        result.encrypted_bytes = sealed.stat().st_size
        if token:
            name = f"{cfg.get('prefix', '')}{sealed.name}"
            result.uploaded = upload(sealed, str(cfg["bucket"]), name, token, client)
        result.status = "success"
    except BackupError as exc:
        result.status, result.error = "failed", str(exc)
    except Exception as exc:  # recorded; the workflow alerts on the exit code
        result.status, result.error = "failed", type(exc).__name__
    finally:
        plain.unlink(missing_ok=True)
        if token:
            sealed.unlink(missing_ok=True)
    if record:
        with sessions.begin() as s:
            row = s.get(JobRun, result.run_id)
            row.ended_at = dt.datetime.now(dt.UTC)
            row.status = result.status
            row.error = result.error
    return result


def passphrase_from_env() -> str | None:
    return os.environ.get("BACKUP_PASSPHRASE") or None
