"""HCH-7: owner-only local health data files + no labs.json cache."""
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server
from server import (
    DATA_DIR as _REAL_DATA_DIR,
)

POSIX = os.name == "posix"


def _mode(p: Path) -> int:
    return stat.S_IMODE(os.stat(p).st_mode)


@pytest.mark.skipif(not POSIX, reason="POSIX modes only")
def test_new_passcode_is_owner_only(tmp_path, monkeypatch):
    target = tmp_path / ".passcode"
    monkeypatch.setattr(server, "_passcode_file", target, raising=False)
    code = server._load_or_create_passcode(target)
    assert code
    assert _mode(target) == 0o600
    # creating under a hostile umask still lands 0600 (atomic os.open)
    target.unlink()
    old = os.umask(0)
    try:
        code2 = server._load_or_create_passcode(target)
    finally:
        os.umask(old)
    assert code2 and _mode(target) == 0o600


@pytest.mark.skipif(not POSIX, reason="POSIX modes only")
def test_existing_passcode_is_tightened(tmp_path):
    target = tmp_path / ".passcode"
    target.write_text("secret-value-123")
    os.chmod(target, 0o644)
    code = server._load_or_create_passcode(target)
    assert code == "secret-value-123"
    assert _mode(target) == 0o600


def test_unrestrictable_passcode_fails_closed(tmp_path, monkeypatch):
    target = tmp_path / ".passcode"
    target.write_text("x")
    monkeypatch.setattr(server, "enforce_owner_only",
                        lambda *a, **k: (_ for _ in ()).throw(server.OwnerOnlyError("nope")),
                        raising=True)
    with pytest.raises((PermissionError, RuntimeError, OSError)):
        server._load_or_create_passcode(target)


@pytest.mark.skipif(not POSIX, reason="POSIX modes only")
def test_write_private_file_atomic_and_symlink_refusal(tmp_path):
    dest = tmp_path / "rec.txt"
    old = os.umask(0o022)
    try:
        server._write_private_file(dest, b"hello")
    finally:
        os.umask(old)
    assert _mode(dest) == 0o600
    assert dest.read_bytes() == b"hello"
    # save_owner_only alias works the same
    server.save_owner_only(dest, b"again")
    assert _mode(dest) == 0o600
    # symlink destinations are refused
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(dest)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises((PermissionError, RuntimeError, OSError)):
        server._write_private_file(link, b"evil")


@pytest.mark.skipif(not POSIX, reason="POSIX modes only")
def test_ensure_private_dir_creates_0700(tmp_path):
    d = tmp_path / "sub" / "records"
    notes = server.ensure_private_dir(d)
    assert d.is_dir() and _mode(d) == 0o700
    assert isinstance(notes, list)
    # pre-existing loose dir is repaired
    os.chmod(d, 0o755)
    server.ensure_private_dir(d)
    assert _mode(d) == 0o700
    # data-dir alias
    assert server.ensure_private_data_dir is not None


@pytest.mark.skipif(not POSIX, reason="POSIX modes only")
def test_enforce_verify_and_symlink(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    os.chmod(f, 0o644)
    assert server.enforce_owner_only(f) is True
    assert _mode(f) == 0o600
    assert server.is_owner_only(f) is True
    assert server.permissions_secure(f) is True
    loose = tmp_path / "b.txt"
    loose.write_text("x")
    os.chmod(loose, 0o644)
    assert server.permissions_secure(loose) is False
    link = tmp_path / "l.txt"
    try:
        link.symlink_to(f)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises((PermissionError, RuntimeError, OSError)):
        server.enforce_owner_only(link)


@pytest.mark.skipif(not POSIX, reason="POSIX modes only")
def test_startup_audit_repairs_and_never_prints_contents(tmp_path, monkeypatch, capsys):
    dd = tmp_path / "data"
    dd.mkdir()
    secret = "SECRET-PHI-VALUE-98765"
    rec = dd / "labs.txt"
    rec.write_text(f"hemoglobin {secret}")
    os.chmod(dd, 0o755)
    os.chmod(rec, 0o644)
    pf = tmp_path / ".passcode"
    pf.write_text("pw")
    os.chmod(pf, 0o644)
    notes = server.audit_permissions(pf, dd)
    cap = capsys.readouterr()
    out = cap.out + cap.err
    # repaired
    assert _mode(dd) == 0o700 and _mode(rec) == 0o600 and _mode(pf) == 0o600
    assert notes
    assert secret not in out and "hemoglobin" not in out
    assert "labs.txt" in out or any("labs.txt" in n for n in notes)
    # aliases agree
    assert server.check_local_permissions is server.audit_permissions
    assert server.startup_permission_check is server.check_startup_permissions
    # quiet when already secure
    notes2 = server.audit_permissions(pf, dd, report=lambda m: None)
    assert notes2 == [] or all("legacy" in n for n in notes2)


@pytest.mark.skipif(not POSIX, reason="POSIX modes only")
def test_startup_check_creates_missing_dir_and_exits_on_bad_passcode(tmp_path, monkeypatch):
    dd = tmp_path / "missing" / "data"
    notes = server.check_startup_permissions(data_dir=dd, passcode_file=tmp_path / "nope")
    assert dd.is_dir() and _mode(dd) == 0o700
    assert isinstance(notes, list)
    # unprotectable passcode -> SystemExit
    pf = tmp_path / ".passcode"
    pf.write_text("x")
    monkeypatch.setattr(server, "enforce_owner_only",
                        lambda *a, **k: (_ for _ in ()).throw(server.OwnerOnlyError("nope")),
                        raising=True)
    with pytest.raises(SystemExit):
        server.check_startup_permissions(passcode_file=pf, data_dir=dd, report=lambda m: None)
    with pytest.raises(SystemExit):
        server.startup_permission_check(passcode_file=pf, data_dir=dd, report=lambda m: None)


def test_perms_repair_env_report_only(tmp_path):
    dd = tmp_path / "data"
    dd.mkdir()
    rec = dd / "r.txt"
    rec.write_text("x")
    if POSIX:
        os.chmod(rec, 0o644)
    pf = tmp_path / ".passcode"
    pf.write_text("pw")
    if POSIX:
        os.chmod(pf, 0o644)
        os.chmod(dd, 0o755)
    notes = server.audit_permissions(pf, dd, repair=False, report=lambda m: None)
    assert any("INSECURE" in n for n in notes)
    if POSIX:
        # report-only leaves modes alone
        assert _mode(rec) == 0o644


def test_windows_acl_paths_mocked(tmp_path, monkeypatch):
    import subprocess as sp
    monkeypatch.setattr(os, "name", "nt")
    calls = []

    class P:
        returncode = 0
        stdout = "Successfully processed 1 files;"

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return P()
    monkeypatch.setattr(sp, "run", fake_run)
    monkeypatch.setattr(server.subprocess, "run", fake_run)
    p = tmp_path / "f.txt"
    p.write_text("x")
    assert server.enforce_owner_only(p) is True
    assert calls and calls[0][0] == "icacls" and "/inheritance:r" in calls[0]

    class Bad:
        returncode = 1
        stdout = ""
        stderr = "Access denied"
    monkeypatch.setattr(sp, "run", lambda *a, **k: Bad())
    monkeypatch.setattr(server.subprocess, "run", lambda *a, **k: Bad())
    with pytest.raises((PermissionError, RuntimeError, OSError)):
        server.enforce_owner_only(p)
    # readback parser: inherited or foreign ACEs are insecure
    monkeypatch.setattr(server, "_current_user", lambda: "brad")
    assert server._windows_acl_owner_only("DESKTOP\\brad:(F)\nSuccessfully processed 1 files;") is True
    assert server._windows_acl_owner_only("DESKTOP\\brad:(I)(F)\n") is False
    assert server._windows_acl_owner_only("Everyone:(F)\n") is False


@pytest.mark.skipif(not POSIX, reason="POSIX modes only")
def test_upload_creates_owner_only_files(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    dd = tmp_path / "uploads"
    monkeypatch.setattr(server, "DATA_DIR", dd)
    monkeypatch.setattr(server, "LEGACY_LABS_JSON", tmp_path / "labs.json")
    client = TestClient(server.app)
    headers = {"Authorization": f"Bearer {server.PASSCODE}"}
    old = os.umask(0o022)
    try:
        r = client.post("/api/upload", headers=headers,
                        files={"file": ("lab.txt", b"GLUCOSE 99 mg/dL", "text/plain")})
    finally:
        os.umask(old)
    assert r.status_code == 200, r.text
    dest = dd / "lab.txt"
    assert dest.exists()
    assert _mode(dd) == 0o700
    assert _mode(dest) == 0o600


@pytest.mark.skipif(not POSIX, reason="POSIX modes only")
def test_build_index_writes_no_labs_json(tmp_path, monkeypatch):
    dd = tmp_path / "data"
    dd.mkdir()
    (dd / "a.txt").write_text("hello world hello")
    monkeypatch.setattr(server, "DATA_DIR", dd)
    monkeypatch.setattr(server, "BASE", tmp_path)
    monkeypatch.setattr(server, "LEGACY_LABS_JSON", tmp_path / "labs.json")
    out = server.build_index()
    assert (tmp_path / "labs.json").exists() is False
    assert "permissions" in out
    # source contains no labs.json writer
    src = Path(server.__file__).read_text()
    assert '("labs.json").write_text' not in src and "('labs.json').write_text" not in src


def test_uninstall_docs_remove_legacy_labs_json():
    root = Path(server.__file__).resolve().parent
    readme = (root / "README.md").read_text()
    assert "labs.json" in readme and ".passcode" in readme
    install = (root / "docs" / "INSTALL.md").read_text()
    assert "labs.json" in install
