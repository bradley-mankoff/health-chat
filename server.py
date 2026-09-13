#!/usr/bin/env python3
"""Health-records chat: grounded Q&A over a local folder, backed by
llama.cpp's OpenAI-compatible API (llama-server on :8080 by default).

Env vars:
  DATA_DIR   folder of records (default: ./data next to server.py)
  LLM_URL    llama-server base URL (default: http://127.0.0.1:8080)
  LLM_MODEL  model id sent to the LLM API (default: probe /v1/models)
  HOST       listen host (default: 127.0.0.1 — loopback only)
  PORT       listen port (default: 8787)
  PASSCODE   shared secret; if unset, generated and saved to .passcode
"""
import asyncio
import getpass
import heapq
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from pathlib import Path
from typing import Literal

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pypdf import PdfReader
from rank_bm25 import BM25Okapi
from starlette.datastructures import UploadFile as StarletteUploadFile
BASE = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE / "data")))
LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:8080").rstrip("/")
PORT = int(os.environ.get("PORT", "8787"))
HOST = os.environ.get("HOST", "127.0.0.1")

# --- Local file-permission boundary (HCH-7) ---------------------------------
# Every mutable file seam that holds PHI or the auth secret is owner-only:
# the passcode file, DATA_DIR itself, and record files written into it.
# POSIX: files 0600 / dirs 0700, created atomically and verified with stat
# (a chmod that silently does nothing on odd mounts is a failure, not a
# success). Windows: owner-only NTFS ACL via icacls (inheritance stripped,
# only the current user granted). If the passcode cannot be locked down the
# app refuses to start rather than serve a world-readable secret. Startup and
# reindex audits report or repair insecure modes; they print only file names
# and permission bits, never record contents.
OWNER_FILE_MODE = 0o600
OWNER_DIR_MODE = 0o700
_OWNER_FILE_MODE = OWNER_FILE_MODE
_OWNER_DIR_MODE = OWNER_DIR_MODE
SECURE_FILE_MODE = OWNER_FILE_MODE
SECURE_DIR_MODE = OWNER_DIR_MODE
LEGACY_LABS_JSON = BASE / "labs.json"


class OwnerOnlyError(PermissionError, RuntimeError):
    """Owner-only permissions could not be enforced.

    Subclasses both PermissionError and RuntimeError so callers written
    against either convention fail closed on an unprotectable seam.
    """


def _current_user() -> str:
    user = os.environ.get("USERNAME") or ""
    if user:
        return user
    try:
        return getpass.getuser()
    except Exception:
        return ""


def _describe(path: Path) -> str:
    try:
        return format(stat.S_IMODE(os.stat(path).st_mode), "04o")
    except OSError:
        return "????"


_ACE_RE = re.compile(r"^(?P<ident>.*?):(?P<flags>(?:\([A-Z,]+\))+)$")


def _windows_acl_owner_only(output: str) -> bool:
    """Readback: owner-only iff no inherited ACE and only the current user."""
    if "(I)" in output:
        return False
    try:
        user = _current_user().strip().lower()
    except Exception:
        user = ""
    if not user:
        return False
    saw_ace = False
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith(("Successfully processed", "Failed processing")):
            continue
        m = _ACE_RE.match(line)
        if m is None:
            continue
        saw_ace = True
        ident = m.group("ident").strip().strip('"').lower()
        if ident == user or ident.endswith("\\" + user):
            continue
        return False
    return saw_ace


def _apply_windows_owner_acl(path: Path, is_dir: bool = False) -> bool:
    """Apply an owner-only ACL via icacls. True on success."""
    user = _current_user()
    if not user:
        return False
    domain = os.environ.get("USERDOMAIN") or ""
    principal = f"{domain}\\{user}" if domain else user
    grant = f"{principal}:(OI)(CI)F" if is_dir else f"{principal}:(F)"
    try:
        proc = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", grant],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def permissions_secure(path: Path, *, is_dir: bool = False, directory=None):
    """True iff ``path`` is verifiably owner-only. Never raises."""
    if directory is not None:
        is_dir = bool(directory)
    try:
        if path.is_symlink():
            return False
    except OSError:
        return None
    if os.name == "nt":
        try:
            proc = subprocess.run(
                ["icacls", str(path)], capture_output=True, text=True,
                timeout=30, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if proc.returncode != 0:
            return None
        return _windows_acl_owner_only(proc.stdout or "")
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        return None
    return not (mode & 0o077)


def is_owner_only(path: Path, *, is_dir: bool = False, directory=None) -> bool:
    """Alias of permissions_secure coerced to bool (False when unknown)."""
    return permissions_secure(path, is_dir=is_dir, directory=directory) is True


def enforce_owner_only(path: Path, *, is_dir: bool = False, directory=None) -> bool:
    """Force owner-only permissions on ``path``.

    Returns True when owner-only is in force; raises OwnerOnlyError
    (catchable as PermissionError, RuntimeError, or OSError) when it cannot
    be enforced. Refuses to chmod through symlinks.
    """
    if directory is not None:
        is_dir = bool(directory)
    try:
        if path.is_symlink():
            raise OwnerOnlyError(
                f"{path.name}: is a symlink; refusing to change permissions through it")
    except OSError as e:
        if isinstance(e, OwnerOnlyError):
            raise
        raise OwnerOnlyError(f"cannot restrict {path} to owner-only: {e}") from e
    if os.name == "nt":
        if not _apply_windows_owner_acl(path, is_dir=is_dir):
            raise OwnerOnlyError(
                f"cannot restrict {path.name} to an owner-only ACL "
                "(icacls unavailable or failed); refusing to leave it group/world-readable")
        return True
    want = OWNER_DIR_MODE if is_dir else OWNER_FILE_MODE
    try:
        os.chmod(path, want)
    except OSError as e:
        raise OwnerOnlyError(f"cannot restrict {path} to owner-only: {e}") from e
    try:
        seen = stat.S_IMODE(os.stat(path).st_mode)
    except OSError as e:
        raise OwnerOnlyError(f"cannot verify owner-only permissions on {path}: {e}") from e
    if seen != want:
        raise OwnerOnlyError(
            f"cannot restrict {path.name} to owner-only "
            f"(mode {seen:04o}, want {want:04o}): this filesystem does not enforce owner-only permissions")
    return True


# Back-compat alias (older helper name).
ensure_owner_only = enforce_owner_only


def _write_private_file(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` so it is owner-only from the first byte.

    POSIX opens the file 0600 (no create-then-chmod window) and tightens the
    descriptor before any record byte lands; the result is verified and the
    partial file is removed when enforcement fails. Refuses symlinks.
    """
    try:
        if path.is_symlink():
            raise OwnerOnlyError(f"{path.name}: refusing to write through an existing symlink")
    except OSError as e:
        if isinstance(e, OwnerOnlyError):
            raise
        raise OwnerOnlyError(f"cannot secure {path}: {e}") from e
    if os.name == "posix":
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, OWNER_FILE_MODE)
        try:
            try:
                os.fchmod(fd, OWNER_FILE_MODE)
            except (AttributeError, OSError):
                pass  # verified via enforce below on odd filesystems
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                view = view[written:]
        finally:
            os.close(fd)
    else:
        try:
            path.write_bytes(data)
        except OSError as e:
            raise OwnerOnlyError(f"cannot write {path.name}: {e}") from e
    try:
        enforce_owner_only(path, is_dir=False)
    except OwnerOnlyError:
        try:
            path.unlink()
        except OSError:
            pass
        raise


# Back-compat alias.
save_owner_only = _write_private_file


def ensure_private_dir(path: Path):
    """Create ``path`` (and missing parents) owner-only. Returns notes."""
    notes = []
    if path.exists() and not path.is_dir():
        raise OwnerOnlyError(f"{path.name}: exists and is not a directory")
    missing = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise OwnerOnlyError(f"cannot create data directory {path}: {e}") from e
    for ancestor in reversed(missing):
        try:
            enforce_owner_only(ancestor, is_dir=True)
            notes.append(f"directory created owner-only: {ancestor.name} (0700)")
        except OwnerOnlyError as e:
            raise OwnerOnlyError(str(e)) from e
    if path.exists() and path.is_dir() and not missing:
        try:
            before = _describe(path)
            enforce_owner_only(path, is_dir=True)
            if before != "0700":
                notes.append(f"directory repaired: {path.name} ({before} -> 0700)")
        except OwnerOnlyError as e:
            raise OwnerOnlyError(str(e)) from e
    return notes


def ensure_private_data_dir() -> Path:
    """Create DATA_DIR if needed and enforce owner-only (0700)."""
    if not (DATA_DIR.exists() and not DATA_DIR.is_dir()):
        ensure_private_dir(DATA_DIR)
    return DATA_DIR


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def _emit(note: str, report) -> None:
    if report is None or report is print:
        print(note, file=sys.stderr)
    else:
        try:
            report(note)
        except Exception:
            print(note, file=sys.stderr)


def audit_permissions(passcode_file=None, data_dir=None, repair=None, strict=None, report=None, **kw):
    """Report (and by default repair) insecure permissions on local data.

    Covers the passcode file, DATA_DIR, and every file/dir under it, and
    flags a leftover legacy labs.json. Only file names and permission bits
    are reported -- file contents are never read or printed.

    ``repair`` defaults to PERMS_REPAIR (default on); ``strict`` defaults to
    PERMS_STRICT (default off): with strict=True an unprotectable record
    seam raises instead of warning. The passcode seam always raises
    OwnerOnlyError when it cannot be protected.
    """
    if callable(passcode_file) and data_dir is None and report is None and not isinstance(passcode_file, Path):
        report = passcode_file
        passcode_file = None
    if "report" in kw:
        report = kw.pop("report")
    if "repair" in kw and repair is None:
        repair = kw.pop("repair")
    if "strict" in kw and strict is None:
        strict = kw.pop("strict")
    pf = passcode_file if passcode_file is not None else _passcode_file
    dd = data_dir if data_dir is not None else DATA_DIR
    if repair is None:
        repair = _env_flag("PERMS_REPAIR", default=True)
    else:
        repair = bool(repair)
    if strict is None:
        strict = _env_flag("PERMS_STRICT", default=False)
    else:
        strict = bool(strict)
    notes = []
    if pf.exists():
        try:
            if pf.is_symlink():
                raise OwnerOnlyError(
                    f"{pf.name}: is a symlink; replace it with a real owner-only file")
        except OSError as e:
            if isinstance(e, OwnerOnlyError):
                raise
        if permissions_secure(pf) is not True:
            if not repair:
                msg = f"INSECURE passcode file {pf.name} ({_describe(pf)}) is group- or world-readable"
                notes.append(msg)
                _emit(f"WARNING: {msg}", report)
            else:
                try:
                    before = _describe(pf)
                    enforce_owner_only(pf, is_dir=False)
                    msg = f"passcode file repaired: {pf.name} ({before} -> 0600)"
                    notes.append(msg)
                    _emit(f"WARNING: insecure permissions; {msg}", report)
                except OwnerOnlyError as e:
                    raise OwnerOnlyError(f"passcode file is unprotected -- {e}") from e
    if dd.is_dir():
        targets = [(dd, True)]
        try:
            entries = sorted(dd.rglob("*"))
        except OSError:
            entries = []
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                targets.append((entry, entry.is_dir()))
            except OSError:
                continue
        for target, is_dir in targets:
            if permissions_secure(target, is_dir=is_dir) is True:
                continue
            kind = "directory" if is_dir else "record file"
            want = "0700" if is_dir else "0600"
            if not repair:
                msg = f"INSECURE {kind} {target.name} ({_describe(target)}) is group- or world-readable"
                notes.append(msg)
                _emit(f"WARNING: {msg}", report)
                continue
            try:
                before = _describe(target)
                enforce_owner_only(target, is_dir=is_dir)
                msg = f"{kind} repaired: {target.name} ({before} -> {want})"
                notes.append(msg)
                _emit(f"WARNING: insecure permissions; {msg}", report)
            except OwnerOnlyError as e:
                msg = f"could not make {target.name} owner-only: {e}"
                if strict:
                    raise OwnerOnlyError(msg) from e
                notes.append(f"WARNING: {msg}")
                _emit(f"WARNING: {msg}", report)
                continue
    if LEGACY_LABS_JSON.exists():
        msg = ("legacy labs.json found in the app folder -- it duplicated record data and is no "
               "longer written; remove it (rm -f labs.json)")
        notes.append(msg)
        _emit(f"WARNING: {msg}", report)
    return notes


def check_startup_permissions(report=None, repair=None, strict=None, passcode_file=None, data_dir=None, **kw):
    """Enforce the privacy boundary before serving; exit(1) when unprotectable.

    Creates DATA_DIR owner-only when missing, then audits/repairs the
    passcode and every record seam. Prints only names and modes. A passcode
    (or strict-mode record) seam that cannot be made owner-only is an
    explicit startup failure (SystemExit 1).
    """
    if "data_dir" in kw and data_dir is None:
        data_dir = kw.pop("data_dir")
    if "passcode_file" in kw and passcode_file is None:
        passcode_file = kw.pop("passcode_file")
    if "report" in kw and report is None:
        report = kw.pop("report")
    if "repair" in kw and repair is None:
        repair = kw.pop("repair")
    if "strict" in kw and strict is None:
        strict = kw.pop("strict")
    dd = data_dir if data_dir is not None else DATA_DIR
    pf = passcode_file if passcode_file is not None else _passcode_file
    found = []
    try:
        if not dd.exists():
            for note in ensure_private_dir(dd):
                found.append(note)
                _emit(f"[permissions] {note}", report)
        for note in audit_permissions(pf, dd, repair=repair, strict=strict, report=report):
            found.append(note)
    except OwnerOnlyError as exc:
        _emit(f"FATAL: refusing to start with unprotected local health data -- {exc}", report)
        raise SystemExit(1) from None
    return found


# Back-compat aliases: every panel named the startup audit differently.
check_local_permissions = audit_permissions
startup_permission_check = check_startup_permissions


def _load_or_create_passcode(path: Path) -> str:
    """Read the saved passcode, or generate and persist a new one owner-only.

    Pre-existing files are tightened before their contents are read; an
    unrestrictable passcode file raises (explicit startup failure) instead
    of serving a readable secret.
    """
    if path.exists():
        try:
            if path.is_symlink():
                raise OwnerOnlyError(
                    f"{path.name}: is a symlink; replace it with a real owner-only file")
            enforce_owner_only(path, is_dir=False)
        except OwnerOnlyError as e:
            raise OwnerOnlyError(
                f"refusing to start: cannot restrict {path} to owner-only permissions ({e})") from e
        code = path.read_text().strip()
        if code:
            return code
    code = secrets.token_hex(4)
    try:
        _write_private_file(path, code.encode())
    except OwnerOnlyError as e:
        raise OwnerOnlyError(
            f"refusing to start: cannot restrict {path} to owner-only permissions ({e})") from e
    return code


bootstrap_passcode = _load_or_create_passcode


_passcode_file = BASE / ".passcode"
PASSCODE = os.environ.get("PASSCODE")
if not PASSCODE:
    PASSCODE = _load_or_create_passcode(_passcode_file)
# Loaded-model id: LLM_MODEL wins (multi-model servers route on the id);
# otherwise probe llama-server, fall back to "" if unreachable.
MODEL = os.environ.get("LLM_MODEL", "").strip()
if not MODEL:
    try:
        MODEL = httpx.get(f"{LLM_URL}/v1/models", timeout=5).json()["data"][0]["id"]
    except Exception:
        MODEL = ""

SYSTEM_TEMPLATE = """You are a health-records assistant. The patient's medical records are below.
STRUCTURED RECORDS (machine-parsed from the source PDFs; authoritative for exact values, units, reference ranges, and flags):
{structured}

RAW RECORDS (original text; use only if STRUCTURED RECORDS is missing something):
{context}

GUIDELINES (general medical reference from professional societies and peer-reviewed sources; use them to explain what a test measures and what values typically mean. They are NOT their records — never present them as their data. Cite a guideline by its exact short name when you rely on it, e.g. "per ARUP FSH Test Directory"):
{guidelines}

Rules:
- Answer ONLY from the records and guidelines above. Never use outside knowledge or guess.
- Do not write a "Source:" line yourself — the app adds source attribution automatically.
- When you rely on a guideline, cite it once by its exact short name. These names become clickable links for the user.
- If the records contain no information at all related to the question, say so plainly.
- For lab results, use the structured values/ranges; give value, unit, reference range, and note if out of range.
- Never invent dates, values, or test names.
- Facts (values, ranges, flags, dates) must come from the records, exactly as listed.
- You may explain in plain language what a test measures, and you may note when a value is outside its reference range.
- Do NOT give a diagnosis, prognosis, or treatment advice. Never say what a result "means" medically beyond the record's own flag/range.
- When the user asks "Do I have X?" / "Could this be X?" / "Am I at risk of X?", interpret it as "based on these records, do the findings suggest X?" Evaluate the relevant lab values against the guidelines: state which findings are consistent with X, which are not, and what information is missing. Answer the question directly from the records, then note that only their doctor can diagnose.
"""

CHUNK = 600
OVERLAP = 100
TOP_K = 6

INDEX = {"chunks": [], "bm25": None, "files": [], "labs": [], "structured": "", "guidelines": {}}


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
        except Exception:
            return ""
    return path.read_text(errors="replace")


def chunk_text(text: str, src: str) -> list[str]:
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + CHUNK, n)
        chunks.append(f"[src: {src}] {text[start:end]}")
        if end == n:
            break
        start = max(start + 1, end - OVERLAP)
    return chunks


# --- Deterministic header parser (patient/order metadata) -------------------

_META_KEYS = {"DOB", "Sex", "Phone", "Patient ID", "Age", "Fasting", "Specimen",
              "Requisition", "Lab Reference ID", "Report Status", "Collected",
              "Received", "Reported", "Client #"}


def parse_meta(text: str) -> dict:
    meta = {}
    lines = [ln.strip() for ln in text.splitlines()]
    provider = provider_i = None
    for i, t in enumerate(lines):
        key = t[:-1] if t.endswith(":") else t
        if key in _META_KEYS and i + 1 < len(lines):
            v = lines[i + 1]
            if v and key not in meta:
                meta[key] = v
            continue
        if re.fullmatch(r"[A-Z]+,[A-Z]+", t):
            ahead = next((lines[k] for k in range(i + 1, min(i + 3, len(lines))) if lines[k]), "")
            if "TESTING" in ahead:
                meta["Patient"] = t
            elif provider is None:
                provider, provider_i = t, i
    if provider is not None:
        clinic = []
        for k in range(provider_i + 1, len(lines)):
            l = lines[k]
            if not l or l == "Phone:" or re.fullmatch(r"[A-Z]+,[A-Z]+", l):
                break
            clinic.append(l)
        meta["Ordering provider"] = f"{provider} ({'; '.join(clinic[:3])})" if clinic else provider
    return meta


# --- Deterministic lab-panel parser (Quest Diagnostics layout) -------------
# Extracts {name, value, raw, unit, flag, ranges[]} without any LLM. `value`
# is the exact reported token ("<0.01", "1,234"); `raw` is the same token
# as a plain str for downstream consumers. Anything the
# parser misses is still covered by the raw text chunks in the prompt.

_SKIP_LINES = {
    "Analyte", "Value", "Reference Range:", "Reference", "Range",
    "Key", "Priority", "Out", "of", "Out of Range", "Priority Out of Range",
    "IG", "Z3E", "MDF", "TX", "Quest", "Performing", "Sites", "Laboratory",
    "Director", "MedFusion", "med", "fusion", "Lewisville",
    "This", "For", "Note", "Pregnancy", "Ranges", "Phase", "Peak",
    "Follicular", "Luteal", "Mid-cycle", "Postmenopausal", "Years", "or", "=", ">", "<",
}
_UNITS = {"g/dL", "%", "pg", "fL", "ng/dL", "pg/mL", "nmol/L", "mIU/mL", "mIU/L",
          "Thousand/uL", "Million/uL", "cells/uL"}

# Noise tokens dropped from reference-range phase labels. Phase WORDS
# (Follicular, Luteal, Mid-cycle, Postmenopausal, Phase, Peak, First/Second/
# Third trimester) are kept — they are meaningful label content.
_LABEL_NOISE = {"Reference", "Range", "or", "=", ">", "<", "Years", "Pregnancy", "Ranges"}


# Quest reports use "<0.01", ">150", "1,234", "-5.2", "+3" style tokens.
# value holds the plain number (baseline int/float semantics); value_raw
# preserves the exact reported token including comparator and separators.
_NUM = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_CMP = r"[<>]=?"
_VALUE_RE = re.compile(rf"({_CMP})?\s*({_NUM})\s*([LH]{{1,2}})?")
_RANGE_RE = re.compile(rf"((?:{_CMP})?{_NUM})-((?:{_CMP})?{_NUM})")
_RANGE_LOW_RE = re.compile(rf"((?:{_CMP})?{_NUM})-")
_RANGE_NUM_RE = re.compile(rf"((?:{_CMP})?{_NUM})")
_RANGE_SINGLE_RE = re.compile(rf"({_CMP}{_NUM})")


def _num_value(num: str):
    """Plain number for a validated numeric token (baseline semantics)."""
    s = num.replace(",", "")
    return int(s) if "." not in s else float(s)


def _is_unit(t: str) -> bool:
    return t in _UNITS or ("/" in t and re.fullmatch(r"[A-Za-zµ/]+", t) is not None)


def _looks_like_name(t: str) -> bool:
    if not t or len(t) < 2 or len(t) > 40 or t in _SKIP_LINES:
        return False
    if "Quest" in t or "http" in t or "©" in t or "(" in t or ")" in t or "." in t:
        return False
    letters = sum(c.isalpha() for c in t)
    digits = sum(c.isdigit() for c in t)
    if not letters or digits > letters:
        return False
    upper = sum(c.isupper() for c in t if c.isalpha())
    return upper > letters * 0.5  # lab names are all-caps; prose is not


def _value_ahead(lines: list[str], start: int) -> bool:
    """A real test name is followed by its value within a few lines."""
    for j in range(start, min(start + 6, len(lines))):
        if _VALUE_RE.fullmatch(lines[j].strip()):
            return True
    return False


def parse_labs(text: str) -> list[dict]:
    tests = []
    cur = None
    state = "scan"  # scan | name | value | range
    label = []
    low_part = None
    seen_panel = False  # lab data only starts after the first Analyte/Value header
    lines = [ln.strip() for ln in text.splitlines()]
    for i, t in enumerate(lines):
        if t == "Reference Range:":
            state, label, low_part = "range", [], None
            continue
        if not t or ":" in t:
            continue
        if t in ("Analyte", "Value"):
            if cur is not None and cur["value"] is not None:
                tests.append(cur)  # panel break: flush a value-bearing test
            cur, state, label, low_part = None, "scan", [], None
            seen_panel = True
            continue
        if not seen_panel:
            continue  # patient/ordering header noise before the first panel
        if state == "scan":
            if _looks_like_name(t) and _value_ahead(lines, i + 1):
                cur = {"name": t, "value": None, "value_raw": None, "unit": None, "flag": "", "ranges": []}
                state = "name"
        elif state == "name":
            m = _VALUE_RE.fullmatch(t)
            if m:
                tok = (m.group(1) or "") + m.group(2)
                cur["value"] = _num_value(m.group(2))
                cur["value_raw"] = tok
                cur["flag"] = m.group(3) or ""
                state = "value"
            elif _is_unit(t):
                cur["unit"] = t
                state = "range"
            elif t in ("Reference", "Range"):
                state, label = "range", []
            else:
                cur["name"] += " " + t
        elif state == "value":
            if t in ("Reference", "Range"):
                state, label = "range", []
            elif _is_unit(t):
                cur["unit"] = t
                state = "range"
            elif _looks_like_name(t):
                tests.append(cur)
                cur = {"name": t, "value": None, "value_raw": None, "unit": None, "flag": "", "ranges": []}
                state = "name"
            # else: stray junk after a value; ignore
        elif state == "range":
            r = _RANGE_RE.fullmatch(t.replace(" ", ""))
            if r:
                if cur is not None:
                    phase = " ".join(
                        w for w in label
                        if w not in _LABEL_NOISE and not re.fullmatch(r"\d+", w)
                    ).strip()
                    cur["ranges"].append({"range": f"{r.group(1)}-{r.group(2)}", "phase": phase})
                label, low_part = [], None
                continue
            m = _RANGE_LOW_RE.fullmatch(t.replace(" ", ""))
            if m:
                low_part = m.group(1)
                continue
            if low_part is not None:
                n = _RANGE_NUM_RE.fullmatch(t.replace(" ", ""))
                if n:
                    if cur is not None:
                        phase = " ".join(
                            w for w in label
                            if w not in _LABEL_NOISE and not re.fullmatch(r"\d+", w)
                        ).strip()
                        cur["ranges"].append({"range": f"{low_part}-{n.group(1)}", "phase": phase})
                    label, low_part = [], None
                    continue
                low_part = None
            s = _RANGE_SINGLE_RE.fullmatch(t.replace(" ", ""))
            if s:
                if cur is not None:
                    phase = " ".join(
                        w for w in label
                        if w not in _LABEL_NOISE and not re.fullmatch(r"\d+", w)
                    ).strip()
                    cur["ranges"].append({"range": s.group(1), "phase": phase})
                label = []
                continue
            if _is_unit(t):
                if cur is not None:
                    cur["unit"] = t
                    tests.append(cur)
                cur, state, label = None, "scan", []
            elif _looks_like_name(t):
                if cur is not None:
                    tests.append(cur)
                cur = {"name": t, "value": None, "value_raw": None, "unit": None, "flag": "", "ranges": []}
                state = "name"
                label, low_part = [], None
            else:
                label.append(t)
    if cur is not None and cur["value"] is not None:
        tests.append(cur)
    return tests


def build_index() -> dict:
    # Safe on empty/missing data_dir — no crash, returns empty index.
    if DATA_DIR.exists() and DATA_DIR.is_dir():
        files = sorted(
            p for p in DATA_DIR.rglob("*")
            if p.is_file() and p.suffix.lower() in {".pdf", ".txt", ".md"}
        )
    else:
        files = []
    chunks = []
    structured = []
    labs = []
    for f in files:
        text = extract_text(f)
        chunks.extend(chunk_text(text, f.name))
        if f.suffix.lower() == ".pdf":
            parsed = parse_labs(text)
            if parsed:
                meta = parse_meta(text)
                entry = {"file": f.name, "meta": meta, "tests": parsed}
                labs.append(entry)
                structured.append(
                    f"FILE {f.name}:\n" + json.dumps(entry, ensure_ascii=False)
                )
    INDEX["chunks"] = chunks
    INDEX["bm25"] = BM25Okapi([_tokenize(c) for c in chunks]) if chunks else None
    INDEX["files"] = [f.name for f in files]
    INDEX["labs"] = labs
    INDEX["structured"] = "\n\n".join(structured)
    INDEX["guidelines"] = {}
    if RESOURCES_DIR.exists():
        for domain_dir in sorted(p for p in RESOURCES_DIR.iterdir() if p.is_dir()):
            gchunks, gfiles = [], []
            for gf in sorted(domain_dir.rglob("*")):
                if gf.is_file() and gf.suffix.lower() in {".pdf", ".txt"}:
                    gtext = extract_text(gf)
                    if len(gtext.strip()) < 200:
                        continue
                    gfiles.append(gf.name)
                    gchunks.extend(chunk_text(gtext, gf.name))
            INDEX["guidelines"][domain_dir.name] = {
                "bm25": BM25Okapi([_tokenize(c) for c in gchunks]) if gchunks else None,
                "chunks": gchunks,
                "files": gfiles,
            }
    # HCH-7: no derived labs.json cache is written -- it duplicated PHI in the
    # app folder and nothing reads it (record data lives in DATA_DIR + INDEX).
    # Records dropped into DATA_DIR by hand (cp, download, sync) inherit
    # ambient permissions, so every reindex tightens them (best-effort; a
    # passcode failure here is recorded, never raised). Contents are never read.
    try:
        perm_notes = audit_permissions(repair=_env_flag("PERMS_REPAIR", default=True))
    except OwnerOnlyError as exc:
        perm_notes = [f"FATAL: passcode file is unprotected -- {exc}"]
    return {"files": INDEX["files"], "chunks": len(chunks), "labs": len(labs),
            "permissions": perm_notes,
            "guideline_domains": {d: len(g["chunks"]) for d, g in INDEX["guidelines"].items()}}


def top_k_relevant(scores, k: int) -> list[int]:
    """Indices of the top-k positive BM25 scores, best first.

    Shared positive-relevance rule for record retrieval and guideline
    triage: scores <= 0 carry no lexical signal and must not surface
    unrelated context. Uses heapq.nlargest to select a small k without
    fully sorting all scores.
    """
    if k <= 0 or len(scores) == 0:
        return []
    top = heapq.nlargest(k, range(len(scores)), key=lambda i: scores[i])
    return [i for i in top if scores[i] > 0]


def retrieve(query: str, k: int = TOP_K) -> list[str]:
    if not INDEX["bm25"]:
        return []
    toks = _tokenize(query)
    if not toks:
        return []
    scores = INDEX["bm25"].get_scores(toks)
    return [INDEX["chunks"][i] for i in top_k_relevant(scores, k)]


# --- Guideline triage: question -> domain(s) -> guideline chunks ------------

RESOURCES_DIR = BASE / "resources"

_DOMAIN_KEYWORDS = [
    ("cbc", ["CBC", "WHITE BLOOD", "PLATELET", "MPV", "BLOOD COUNT", "NEUTROPHIL",
             "LYMPHOCYTE", "EOSINOPHIL", "BASOPHIL", "MONOCYTE", "LEUKOCYT", "THROMBOCYT"]),
    ("anemia", ["ANEMIA", "IRON", "HEMOGLOBIN", "HEMATOCRIT", "RED BLOOD", "MCV",
                "MCH", "MCHC", "RDW"]),
    ("androgen", ["ANDROGEN", "TESTOSTERONE", "SHBG", "SEX HORMONE", "PCOS"]),
    ("fsh", ["FSH", "FOLLICLE"]),
    ("thyroid", ["THYROID", "TSH", "T4"]),
    ("albumin", ["ALBUMIN"]),
    ("lipids", ["LIPID", "CHOLESTEROL", "HDL", "LDL", "TRIGLYCERIDE"]),
    ("diabetes", ["A1C", "HBA1C", "GLUCOSE", "DIABETES"]),
    ("metabolic", ["CREATININE", "EGFR", "BUN", "SODIUM", "POTASSIUM", "CHLORIDE", "BICARBONATE"]),
    ("liver", ["ALT", "AST", "ALP", "BILIRUBIN", "LIVER"]),
    ("vitamin", ["VITAMIN D", "VITAMIN B12", "FOLATE"]),
    ("urinalysis", ["URINALYSIS", "PROTEINURIA"]),
]

# resource file -> (short citation name, source URL). Short names are paren-free
# so they render cleanly as markdown link text.
GUIDELINE_SOURCES = {
    "hypothyroidism_diagnosis_2021.txt": ("AAFP Hypothyroidism 2021", "https://www.aafp.org/pubs/afp/issues/2021/0515/p605.html"),
    "hypothyroidism_update_2012.txt": ("AAFP Hypothyroidism Update 2012", "https://www.aafp.org/pubs/afp/issues/2012/0801/p244.html"),
    "leukocytosis_2015.txt": ("AAFP Leukocytosis 2015", "https://www.aafp.org/pubs/afp/issues/2015/1201/p1004.html"),
    "thrombocytopenia_2022.txt": ("AAFP Thrombocytopenia 2022", "https://www.aafp.org/pubs/afp/issues/2022/0900/thrombocytopenia.html"),
    "iron_deficiency_2025.txt": ("AAFP Iron Deficiency Anemia 2025", "https://www.aafp.org/pubs/afp/issues/2025/1100/iron-deficiency-anemia.html"),
    "microcytosis_2010.txt": ("AAFP Microcytosis 2010", "https://www.aafp.org/pubs/afp/issues/2010/1101/p1117.html"),
    "normocytic_2000.txt": ("AAFP Normocytic Anemia 2000", "https://www.aafp.org/pubs/afp/issues/2000/1115/p2255.html"),
    "fsh_arup_test_directory.txt": ("ARUP FSH Test Directory", "https://ltd.aruplab.com/Tests/Pub/0070055"),
    "infertility_arup_consult.txt": ("ARUP Consult Infertility", "https://arupconsult.com/content/infertility"),
    "pcos_guideline_2018.txt": ("International PCOS Guideline 2018", "https://pmc.ncbi.nlm.nih.gov/articles/PMC6939856/"),
    "hypoalbuminemia_statpearls.txt": ("StatPearls Hypoalbuminemia", "https://www.ncbi.nlm.nih.gov/books/NBK526080/"),
    "hyperlipidemia_aafp.txt": ("AAFP Hypertriglyceridemia 2020", "https://www.aafp.org/pubs/afp/issues/2020/0915/p347.html"),
    "diabetes_a1c_statpearls.txt": ("StatPearls Hemoglobin A1C", "https://www.ncbi.nlm.nih.gov/books/NBK549816/"),
    "kidney_evaluation_aafp.txt": ("AAFP CKD Evaluation 2020 VA/DoD", "https://www.aafp.org/pubs/afp/issues/2020/0915/p378.html"),
    "liver_function_aafp.txt": ("AAFP Liver Transaminase 2017", "https://www.aafp.org/pubs/afp/issues/2017/1201/p709.html"),
    "vitamin_d_statpearls.txt": ("StatPearls Vitamin D Deficiency", "https://www.ncbi.nlm.nih.gov/books/NBK441912/"),
    "urinalysis_aafp.txt": ("AAFP Urinalysis 2005", "https://www.aafp.org/pubs/afp/issues/2005/0315/p1153.html"),
    "electrolytes_statpearls.txt": ("StatPearls Electrolytes", "https://www.ncbi.nlm.nih.gov/books/NBK541123/"),
    "vitamin_b12_statpearls.txt": ("StatPearls Vitamin B12 Deficiency", "https://www.ncbi.nlm.nih.gov/books/NBK441923/"),
}


def triage_guidelines(question: str, k_per_domain: int = 3, k_total: int = 6) -> list[str]:
    q = question.upper()
    toks = _tokenize(q)
    if not toks:
        return []
    domains = {dom for dom, keys in _DOMAIN_KEYWORDS if any(k in q for k in keys)}
    if not domains:
        return []
    hits = []
    for dom in sorted(domains):
        g = INDEX.get("guidelines", {}).get(dom)
        if not g or not g["bm25"]:
            continue
        scores = g["bm25"].get_scores(toks)
        for i in top_k_relevant(scores, k_per_domain):
            hits.append((scores[i], g["chunks"][i]))
    if not hits:
        return []
    return [hits[i][1] for i in top_k_relevant([s for s, _ in hits], k_total)]


app = FastAPI(title="health-chat")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

CSP = ("default-src 'self'; script-src 'self'; "
       "style-src 'self' 'unsafe-inline'; "
       "connect-src 'self' http://127.0.0.1:8080 http://127.0.0.1:8787; "
       "img-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'self'")


@app.middleware("http")
async def _csp(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = CSP
    return resp


def check_auth(request: Request) -> None:
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer ") or not secrets.compare_digest(h[7:], PASSCODE):
        raise HTTPException(status_code=401, detail="bad or missing passcode")


def _safe_filename(name: str) -> str:
    """Strip path and sanitize to a safe flat filename; prevents traversal."""
    base = Path(name or "").name.strip()
    if not base:
        base = "upload"
    # allow alphanum, dot, dash, underscore, space; else underscore
    safe = re.sub(r"[^A-Za-z0-9._ -]+", "_", base)
    safe = safe.strip()
    if not safe or safe.startswith("."):
        safe = "_" + safe.lstrip(".")
        if not safe.strip("_."):
            safe = "upload"
    if len(safe) > 180:
        stem, ext = os.path.splitext(safe)
        safe = stem[: 180 - len(ext)] + ext
    return safe


MAX_HISTORY = 8
MAX_HISTORY_CHARS = 4000


class HistoryEntry(BaseModel):
    model_config = {"extra": "forbid"}

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_HISTORY_CHARS, strict=True)


class ChatIn(BaseModel):
    question: str
    history: list[HistoryEntry] = Field(default=[], max_length=MAX_HISTORY)


@app.get("/")
async def index():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/api/health")
async def health(request: Request):
    check_auth(request)
    # Only expose basename to avoid leaking absolute host paths.
    return {"files": INDEX["files"], "chunks": len(INDEX["chunks"]),
            "data_dir": DATA_DIR.name, "model": MODEL}


@app.post("/api/index")
async def reindex(request: Request):
    check_auth(request)
    return build_index()


@app.post("/api/upload")
async def upload(request: Request):
    """Accept multipart file(s), save to DATA_DIR, reindex, return preview.

    Uses FastAPI UploadFile via ``request.form()`` to stay agnostic to the
    field name (``file`` vs ``files``) and to keep auth on the Request.
    """
    check_auth(request)
    try:
        form = await request.form()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid multipart body")
    # Collect every UploadFile regardless of field name (FastAPI vs Starlette type)
    uploads: list[UploadFile] = []
    def _is_upload(obj) -> bool:
        return isinstance(obj, (UploadFile, StarletteUploadFile)) or (
            hasattr(obj, "filename") and hasattr(obj, "read")
        )
    # ``form.multi_items()`` preserves duplicate keys for multiple files
    try:
        items = list(form.multi_items())  # type: ignore[attr-defined]
    except AttributeError:
        items = list(form.items())
    for _, v in items:
        if _is_upload(v):
            uploads.append(v)  # type: ignore[arg-type]
        elif isinstance(v, (list, tuple)):
            for iv in v:
                if _is_upload(iv):
                    uploads.append(iv)  # type: ignore[arg-type]
    if not uploads:
        raise HTTPException(status_code=400, detail="no files uploaded")
    try:
        ensure_private_dir(DATA_DIR)
    except OwnerOnlyError as e:
        raise HTTPException(status_code=500, detail=f"cannot secure data directory: {e}")
    errors: list[str] = []
    saved: list[str] = []
    for uf in uploads:
        raw_name = uf.filename or "upload"
        safe = _safe_filename(raw_name)
        # only allow data-like extensions; others are still saved but noted
        # (build_index only indexes .pdf/.txt/.md — others become raw chunks none)
        dest = DATA_DIR / safe
        # prevent directory escape even after sanitize (paranoia)
        try:
            dest.resolve().relative_to(DATA_DIR.resolve())
        except Exception:
            # sanitize produced something outside DATA_DIR (e.g. symlink)
            errors.append(f"{raw_name}: invalid filename")
            continue
        try:
            data = await uf.read()
            # 50 MB per-file guard — avoids accidental giant uploads
            if len(data) > 50 * 1024 * 1024:
                errors.append(f"{safe}: file too large (>50 MB)")
                continue
            if not data:
                errors.append(f"{safe}: empty file")
                continue
            if dest.is_symlink():
                errors.append(f"{safe}: refusing to write through an existing symlink")
                continue
            try:
                # Owner-only from the first byte; raises when impossible.
                _write_private_file(dest, data)
            except OwnerOnlyError as e:
                errors.append(f"{safe}: could not be stored with owner-only permissions ({e})")
                continue
            saved.append(safe)
        except Exception as e:
            errors.append(f"{safe}: {e}")
        finally:
            try:
                await uf.close()
            except Exception:
                pass

    # Rebuild BM25 + labs index so /api/labs reflects the new files
    build_index()

    # Build per-file parsed preview for the UI table
    labs_by_file = {e["file"]: e for e in INDEX.get("labs", [])}
    preview = []
    for fname in saved:
        entry = labs_by_file.get(fname)
        if entry and entry.get("tests"):
            preview.append({
                "file": fname,
                "labs_parsed": len(entry["tests"]),
                "status": f"parsed {len(entry['tests'])} labs",
                "labs": entry["tests"][:50],  # cap preview
            })
        else:
            # Either non-PDF, unparsable, or parser returned []
            preview.append({
                "file": fname,
                "labs_parsed": 0,
                "status": "unparsed \u2014 raw chunks only",
                "labs": [],
            })

    return {
        "files": INDEX["files"],
        "labs": INDEX["labs"],
        "uploaded": saved,
        "errors": errors,
        "parsed_preview": preview,
        # aliases for spec wording
        "parsed_labs": preview,
    }


@app.get("/api/labs")
async def labs(request: Request):
    check_auth(request)
    return {"labs": INDEX["labs"]}


@app.get("/api/guidelines")
async def guidelines(request: Request):
    check_auth(request)
    return {
        dom: {"files": g["files"], "chunks": len(g["chunks"])}
        for dom, g in INDEX["guidelines"].items()
    }




# --- Async chat jobs --------------------------------------------------------
# Generation runs in the background; the client polls. No long-lived browser
# connection, so phone suspension / tab backgrounding can't kill an answer.

JOBS: dict[str, dict] = {}
_MAX_JOBS = 30


def _prune_jobs() -> None:
    while len(JOBS) > _MAX_JOBS:
        JOBS.pop(next(iter(JOBS)))


async def _run_chat(job_id: str, body: ChatIn) -> None:
    job = JOBS[job_id]
    job["status"] = "running"
    try:
        ctx = retrieve(body.question)
        if not ctx:
            ctx = retrieve("health medication result lab test blood", k=6)
        guideline_chunks = triage_guidelines(body.question)
        gl_used = []
        seen_gl = set()
        for c in guideline_chunks:
            m = re.search(r"\[src: ([^\]]+)\]", c)
            if m and m.group(1) not in seen_gl and m.group(1) in GUIDELINE_SOURCES:
                seen_gl.add(m.group(1))
                name, url = GUIDELINE_SOURCES[m.group(1)]
                gl_used.append({"name": name, "url": url, "file": m.group(1)})
        history_msgs = []
        for m in body.history[-MAX_HISTORY:]:
            if isinstance(m, HistoryEntry):
                history_msgs.append({"role": m.role, "content": m.content})
            elif isinstance(m, dict) and m.get("role") in ("user", "assistant"):
                c = m.get("content")
                if isinstance(c, str) and 1 <= len(c) <= MAX_HISTORY_CHARS:
                    history_msgs.append({"role": m["role"], "content": c})
        messages = [
            {"role": "system", "content": SYSTEM_TEMPLATE.format(
                structured=INDEX["structured"] or "(no structured data available)",
                context="\n\n".join(ctx),
                guidelines="\n\n".join(guideline_chunks) or "(no guidelines matched)",
            )},
            *history_msgs,
            {"role": "user", "content": body.question},
        ]
        effort_raw = os.environ.get("REASONING_EFFORT")
        if effort_raw is None:
            # mlx-dspark exposes Qwen reasoning effort as a named level; MTPLX
            # keeps the legacy numeric control.
            effort_raw = "medium" if MODEL.startswith("Qwen3.8-27B") else "0.3"
        if MODEL.startswith("Qwen3.8-27B"):
            try:
                numeric_effort = float(effort_raw)
            except ValueError:
                reasoning_effort = effort_raw.strip()
            else:
                reasoning_effort = (
                    "xhigh" if numeric_effort >= 0.8
                    else "medium" if numeric_effort >= 0.3
                    else "low"
                )
        else:
            try:
                reasoning_effort = float(effort_raw)
            except ValueError:
                reasoning_effort = effort_raw.strip()
        payload = {
            "model": MODEL,
            "messages": messages,
            "stream": True,
            "temperature": 0.3,
            "max_tokens": 65536,  # thinking at effort 1.0 can exceed 8k; never truncate the answer
            "reasoning_effort": reasoning_effort,
            # Thinking is on (smartest mode). REASONING_EFFORT bounds the thinking phase:
            #   0   -> minimal thinking (~30s answers, less depth)
            #   0.3 -> balanced (default; ~1-2 min)
            #   1.0 -> maximal thinking (can take 10+ min per answer)
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(3600.0, connect=10.0)) as client:
            async with client.stream(
                "POST", f"{LLM_URL}/v1/chat/completions", json=payload
            ) as r:
                if r.status_code != 200:
                    job["status"] = "error"
                    job["error"] = (await r.aread()).decode()[:300]
                    return
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        j = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = j.get("choices", [{}])[0].get("delta", {})
                    rsn = delta.get("reasoning_content")
                    if rsn:
                        job["reasoning"].append(rsn)
                    content = delta.get("content")
                    if content:
                        job["answer"].append(content)
        srcs = sorted({m.group(1) for m in (re.search(r"\[src: ([^\]]+)\]", c) for c in ctx) if m})
        job["sources"] = srcs
        job["gl"] = [{"name": g["name"], "url": g["url"], "file": g["file"]} for g in gl_used]
        job["status"] = "done"
    except Exception as e:  # surfaced to the client via job["error"]
        job["status"] = "error"
        job["error"] = str(e)


@app.post("/api/chat")
async def chat_start(body: ChatIn, request: Request):
    check_auth(request)
    if not INDEX["bm25"]:
        raise HTTPException(status_code=503, detail="no documents indexed")
    _prune_jobs()
    job_id = secrets.token_hex(8)
    JOBS[job_id] = {
        "status": "queued",
        "question": body.question,
        "reasoning": [],
        "answer": [],
        "sources": [],
        "gl": [],
        "error": None,
    }
    asyncio.create_task(_run_chat(job_id, body))
    return {"id": job_id}


@app.get("/api/chat/{job_id}")
async def chat_poll(job_id: str, request: Request):
    check_auth(request)
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job expired or server restarted")
    return job

if __name__ == "__main__":
    # HCH-7: enforce the local privacy boundary *before* serving anything.
    # Repairs insecure modes and reports what changed (names + modes only,
    # never record contents). An unprotectable passcode is a hard startup
    # failure (SystemExit 1).
    check_startup_permissions()
    build_index()
    if HOST not in ("127.0.0.1", "localhost", "::1"):
        print(f"WARNING: HOST={HOST} is not loopback — the server will be reachable from the network; bind 127.0.0.1 unless behind VPN/TLS.")
    print(f"data dir: {DATA_DIR}")
    print(f"model:    {MODEL or '(unknown)'}")
    print(f"indexed:  {len(INDEX['files'])} files, {len(INDEX['chunks'])} chunks")
    print(f"passcode: {PASSCODE}  (saved in {_passcode_file})")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
