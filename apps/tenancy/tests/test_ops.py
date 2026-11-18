"""v0.11.0 A4 and A10: backup and restore, container and compose checks.

The backup tests run the real scripts against the test database in a running PostgreSQL
container. Set DB_CONTAINER to that container's name (and have `docker` and `bash` available);
otherwise they are skipped.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from apps.accounts.tests.helpers import make_college
from apps.tenancy.services import college_context
from apps.workflow.tests.helpers import make_wf_env, signed

ROOT = Path(__file__).resolve().parents[3]
CONTAINER = os.environ.get("DB_CONTAINER", "")
SCRATCH = "attainment_restore_ops"
PASSPHRASE = "a long test passphrase, not a real one"


def _bash() -> str | None:
    """A real bash. On Windows `bash` on PATH can be the WSL launcher, so Git's is preferred."""
    for candidate in (os.environ.get("BASH_EXE"), r"C:\Program Files\Gitinash.exe"):
        if candidate and Path(candidate).exists():
            return candidate
    found = shutil.which("bash")
    return None if found is None or "system32" in found.lower() else found


BASH = _bash()
needs_docker = pytest.mark.skipif(
    not (CONTAINER and shutil.which("docker") and BASH and shutil.which("openssl")),
    reason="set DB_CONTAINER to a running PostgreSQL container (and have docker, bash, openssl)",
)


def _sh(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    full = {**os.environ, "DB_CONTAINER": CONTAINER, "POSTGRES_USER": "postgres", **(env or {})}
    return subprocess.run(  # noqa: S603 - a fixed list of our own scripts
        [BASH or "bash", *args],
        cwd=ROOT,
        env=full,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def _psql(database: str, query: str) -> str:
    result = subprocess.run(  # noqa: S603
        ["docker", "exec", CONTAINER, "psql", "-U", "postgres", "-d", database, "-At", "-c", query],
        capture_output=True, text=True, check=True, timeout=60,
    )  # fmt: skip
    return result.stdout.strip()


def _tables(database: str) -> list[str]:
    rows = _psql(database, "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1")
    return rows.splitlines()


def _counts(database: str) -> dict[str, int]:
    return {t: int(_psql(database, f'SELECT count(*) FROM "{t}"')) for t in _tables(database)}


@pytest.mark.ops
@needs_docker
def test_a4_backup_restore_gives_equal_rows_and_signed_results_and_a_wrong_key_fails(
    committed_db: None, tmp_path: Path
) -> None:
    w = make_wf_env()
    with college_context(w.college.id):
        signed(w)
    make_college("zz")  # a second college in the dump
    env = {
        "BACKUP_DIR": tmp_path.as_posix(),
        "BACKUP_PASSPHRASE": PASSPHRASE,
        "POSTGRES_DB": "attainment_test",
    }
    made = _sh("scripts/ops/backup.sh", env=env)
    assert made.returncode == 0, made.stderr
    backup = Path(made.stdout.strip().splitlines()[-1])
    assert backup.exists() and backup.stat().st_size > 1000
    assert (tmp_path / (backup.name + ".sha256")).exists()
    assert b"PGDMP" not in backup.read_bytes()[:64]  # encrypted, not a plain dump
    try:
        wrong = _sh("scripts/ops/restore.sh", str(backup), SCRATCH,
                    env={**env, "BACKUP_PASSPHRASE": "the wrong key"})  # fmt: skip
        assert wrong.returncode != 0 and "wrong passphrase" in wrong.stderr
        assert (
            _psql("postgres", f"SELECT count(*) FROM pg_database WHERE datname='{SCRATCH}'") == "0"
        )
        damaged = tmp_path / "damaged.dump.enc"
        damaged.write_bytes(backup.read_bytes()[:-100])
        (tmp_path / "damaged.dump.enc.sha256").write_text(
            (tmp_path / (backup.name + ".sha256")).read_text().replace(backup.name, damaged.name)
        )
        assert _sh("scripts/ops/restore.sh", str(damaged), SCRATCH, env=env).returncode != 0

        done = _sh("scripts/ops/restore.sh", str(backup), SCRATCH, env=env)
        assert done.returncode == 0, done.stderr
        assert _counts(SCRATCH) == _counts("attainment_test")  # row counts equal, table by table
        query = "SELECT content_hash FROM results_calculationrun WHERE signed ORDER BY 1"
        assert _psql(SCRATCH, query) == _psql("attainment_test", query) != ""
        policies = "SELECT count(*) FROM pg_policies WHERE schemaname='public'"
        assert _psql(SCRATCH, policies) == _psql("attainment_test", policies)  # RLS came along
        forced = "SELECT count(*) FROM pg_class WHERE relforcerowsecurity"
        assert _psql(SCRATCH, forced) == _psql("attainment_test", forced)
    finally:
        _psql("postgres", f'DROP DATABASE IF EXISTS "{SCRATCH}" WITH (FORCE)')


@pytest.mark.ops
@needs_docker
def test_a_backup_without_a_passphrase_is_refused(tmp_path: Path) -> None:
    result = _sh("scripts/ops/backup.sh", env={"BACKUP_DIR": tmp_path.as_posix(),
                                              "BACKUP_PASSPHRASE": ""})  # fmt: skip
    assert result.returncode != 0 and "BACKUP_PASSPHRASE" in result.stderr
    assert not list(tmp_path.iterdir())


# A10: the container and compose files ------------------------------------------------------
def test_a10_the_image_runs_as_a_non_root_user_and_holds_no_secrets() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in dockerfile.splitlines() if ln.strip() and not ln.startswith("#")]
    users = [i for i, ln in enumerate(lines) if ln.startswith("USER ")]
    cmd = next(i for i, ln in enumerate(lines) if ln.startswith("CMD "))
    assert users and lines[users[-1]] != "USER root" and users[-1] < cmd
    assert not re.search(
        r"(?i)^(ENV|ARG)\s+\S*(PASSWORD|SECRET|TOKEN|KEY)\S*=\s*\S+", dockerfile, re.M
    )
    assert not re.search(r"(?i)COPY\s+.*(\.env|data/private|backups)", dockerfile)
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    assert {".env", "data", "backups", ".git"} <= set(ignored)


class _ComposeLoader(yaml.SafeLoader):
    """Reads Compose files, which add the `!reset` tag (empty the inherited value)."""


_ComposeLoader.add_constructor("!reset", lambda loader, node: [])


def test_a10_production_compose_hides_the_database_and_locks_the_app_down() -> None:
    base = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    prod = yaml.load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"), _ComposeLoader)  # noqa: S506 - our own file, safe loader subclass
    assert prod["services"]["db"]["ports"] == []  # not published in production
    assert base["services"]["db"]["ports"][0].startswith("127.0.0.1:")  # never on all interfaces
    app = prod["services"]["app"]
    assert app["read_only"] is True and "no-new-privileges:true" in app["security_opt"]
    assert app["cap_drop"] == ["ALL"]
    assert "ops" in prod["services"] and prod["services"]["ops"]["profiles"] == ["ops"]
    assert (
        "POSTGRES_PASSWORD" not in base["services"]["app"]["environment"]
    )  # the web app has no superuser login
    for name in ("db", "app", "caddy"):
        assert prod["services"][name]["logging"]["options"]["max-size"]
