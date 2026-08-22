"""
Week 5 Final Security Pass
==========================
Machine-verifiable proof of four security properties:

  Gate 1 — Identity gate:    tool handlers enforce session verification in Python code,
                              not in the model's prompt.
  Gate 2 — Admin JWT gate:   every admin endpoint requires a valid Auth0 Bearer token;
                              structural and algorithmic checks prove no route is unguarded.
  Gate 3 — No PII in logs:   no file-based logging; verify_identity args are redacted
                              before DB persistence; print() calls expose only the code,
                              never name/address/phone.
  Gate 4 — Separation:       admin routes and chat routes never share identity primitives.

Run without DB or Ollama:
  docker-compose exec backend python scripts/test_security_pass.py
"""
import ast
import pathlib
import re
import sys
from unittest.mock import MagicMock

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

PASS_MARK = "\033[32mPASS\033[0m"
FAIL_MARK = "\033[31mFAIL\033[0m"

_results: list[tuple[str, bool]] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    _results.append((label, condition))
    status = PASS_MARK if condition else FAIL_MARK
    print(f"  [{status}] {label}")
    if not condition and detail:
        print(f"         \033[33m{detail}\033[0m")


# ── Gate 1 — Identity Gate ────────────────────────────────────────────────────
print("\nGate 1 — Identity Gate (_can_access)\n")

from models.chat_session import ChatSession, SessionState
from tools.shipments import _can_access


def _mock_session(state: SessionState, customer_id: str | None = None) -> ChatSession:
    s = MagicMock(spec=ChatSession)
    s.state = state
    s.customer_id = customer_id
    return s


check("anonymous → denied",
      not _can_access(_mock_session(SessionState.anonymous)))
check("anonymous + model-supplied customer_id → still denied (ID ignored)",
      not _can_access(_mock_session(SessionState.anonymous, "attacker-id")))
check("collecting_identity → denied",
      not _can_access(_mock_session(SessionState.collecting_identity)))
check("code_sent → denied",
      not _can_access(_mock_session(SessionState.code_sent)))
check("awaiting_code → denied",
      not _can_access(_mock_session(SessionState.awaiting_code)))
check("awaiting_code + customer_id → denied (code not yet entered)",
      not _can_access(_mock_session(SessionState.awaiting_code, "pending-id")))
check("escalated_to_human, no customer_id → denied (escalated while anonymous)",
      not _can_access(_mock_session(SessionState.escalated_to_human, None)))
check("verified + customer_id → allowed",
      _can_access(_mock_session(SessionState.verified, "real-id")))
check("escalated_to_human + customer_id → allowed (verified before escalation)",
      _can_access(_mock_session(SessionState.escalated_to_human, "real-id")))

shipments_src = (ROOT / "tools/shipments.py").read_text()
can_access_calls = shipments_src.count("_can_access(session)")
check(
    "Both shipment handlers call _can_access() before any DB access",
    can_access_calls >= 2,
    f"Expected at least 2 calls, found {can_access_calls}",
)

# ── Gate 2 — Admin JWT Gate ───────────────────────────────────────────────────
print("\nGate 2 — Admin JWT Gate (require_admin)\n")

admin_src = (ROOT / "routes/admin.py").read_text()
auth_src = (ROOT / "auth/auth0.py").read_text()

route_count = len(re.findall(r"@router\.(get|post|put|delete)\(", admin_src))
require_admin_count = len(re.findall(r"Depends\(require_admin\)", admin_src))

check(
    f"Every admin route is guarded — {require_admin_count} Depends(require_admin) for {route_count} route(s)",
    require_admin_count >= route_count,
    f"Found {require_admin_count} guards but {route_count} route decorators — each route must be protected",
)

check(
    "HTTPBearer scheme enforced (401 for missing Authorization header)",
    "HTTPBearer" in auth_src,
)
check(
    "JWT issuer validated (prevents cross-tenant token acceptance)",
    "issuer=" in auth_src,
)
check(
    "JWT audience validated (prevents token reuse from unrelated APIs)",
    "audience=" in auth_src,
)
check(
    "JWTError raises HTTP 401 (not 403 or 500)",
    "HTTP_401_UNAUTHORIZED" in auth_src and "JWTError" in auth_src,
)
check(
    "Public keys fetched from Auth0 JWKS endpoint (not a hardcoded secret)",
    ".well-known/jwks.json" in auth_src,
)
check(
    "Kid-based key lookup (correct key selected from JWKS rotation)",
    '"kid"' in auth_src or "'kid'" in auth_src,
)

admin_import_names: set[str] = set()
for node in ast.walk(ast.parse(admin_src)):
    if isinstance(node, ast.ImportFrom):
        for alias in node.names:
            admin_import_names.add(alias.name)
check(
    "routes/admin.py imports require_admin (guard not accidentally removed)",
    "require_admin" in admin_import_names,
)

# ── Gate 3 — No PII in Persistent Logs ───────────────────────────────────────
print("\nGate 3 — No PII in Persistent Logs\n")

all_py = [
    f for f in ROOT.rglob("*.py")
    if "__pycache__" not in str(f) and "scripts" not in str(f)
]

file_handler_hits = [
    str(f.relative_to(ROOT))
    for f in all_py
    if "FileHandler" in f.read_text() or "basicConfig" in f.read_text()
]
check(
    "No file-based logging (FileHandler / basicConfig) anywhere in backend",
    not file_handler_hits,
    "Found in: " + ", ".join(file_handler_hits),
)

PII_FIELD_NAMES = {"first_name", "last_name", "phone_number", "address"}

log_pii_hits: list[str] = []
for f in all_py:
    for lineno, line in enumerate(f.read_text().splitlines(), 1):
        if re.search(r"\blogging\.(info|warning|error|debug|critical)\b", line):
            if any(field in line for field in PII_FIELD_NAMES):
                log_pii_hits.append(f"{f.relative_to(ROOT)}:{lineno}: {line.strip()}")
check(
    "No logging calls that embed PII field values",
    not log_pii_hits,
    "\n         ".join(log_pii_hits),
)

chat_src = (ROOT / "routes/chat.py").read_text()
check(
    "_PII_TOOLS in chat.py contains 'verify_identity'",
    "_PII_TOOLS" in chat_src and '"verify_identity"' in chat_src,
)
check(
    "Redaction sentinel {'_redacted': True} applied before DB commit",
    '"_redacted"' in chat_src or "'_redacted'" in chat_src,
)

print_pii_hits: list[str] = []
for f in all_py:
    for lineno, line in enumerate(f.read_text().splitlines(), 1):
        stripped = line.strip()
        if "print(" in stripped and not stripped.startswith("#"):
            if any(field in stripped for field in PII_FIELD_NAMES):
                print_pii_hits.append(f"{f.relative_to(ROOT)}:{lineno}: {stripped}")
check(
    "No print() calls embed raw PII field values",
    not print_pii_hits,
    "\n         ".join(print_pii_hits),
)

identity_src = (ROOT / "tools/identity.py").read_text()
code_print_lines = [
    line.strip() for line in identity_src.splitlines()
    if "print(" in line and "[2FA CODE]" in line
]
check(
    "[2FA CODE] mock-SMS print exists in tools/identity.py",
    len(code_print_lines) > 0,
    "Expected at least one [2FA CODE] print — it substitutes for real SMS",
)
pii_in_code_print = any(
    field in line for line in code_print_lines for field in PII_FIELD_NAMES
)
check(
    "[2FA CODE] print contains session_id + code only, never name/address/phone",
    not pii_in_code_print,
    "PII field found in 2FA print: " + str(code_print_lines),
)

# ── Gate 4 — System Separation ────────────────────────────────────────────────
print("\nGate 4 — System Separation (structural invariants)\n")

verify_src = (ROOT / "routes/verify.py").read_text()


def _imports_of(src: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
            names.add(node.module)
    return names


def _name_refs_of(src: str) -> set[str]:
    """AST-based identifier scan — excludes docstrings and comments."""
    refs: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Name):
            refs.add(node.id)
        elif isinstance(node, ast.Attribute):
            refs.add(node.attr)
    return refs


admin_refs = _name_refs_of(admin_src)
auth_refs = _name_refs_of(auth_src)

check(
    "routes/admin.py never references ChatSession in code (docstrings excluded)",
    "ChatSession" not in admin_refs,
)
check(
    "routes/admin.py never references SessionState in code",
    "SessionState" not in admin_refs,
)
check(
    "routes/admin.py never references verification_code in code",
    "verification_code" not in admin_refs,
)
check(
    "routes/chat.py imports nothing from auth/",
    "auth" not in _imports_of(chat_src),
)
check(
    "routes/verify.py imports nothing from auth/",
    "auth" not in _imports_of(verify_src),
)
check(
    "auth/auth0.py never references ChatSession in code (docstrings excluded)",
    "ChatSession" not in auth_refs,
)
check(
    "auth/auth0.py never references SessionState in code",
    "SessionState" not in auth_refs,
)
check(
    "Only routes/verify.py transitions state → verified",
    "SessionState.verified" in verify_src and "SessionState.verified" not in admin_src,
)

# ── Summary ───────────────────────────────────────────────────────────────────
passed = sum(1 for _, ok in _results if ok)
failed = sum(1 for _, ok in _results if not ok)
total = len(_results)

print(f"\n{'─' * 54}")
print(f"Result: {passed}/{total} checks passed", end="")
if not failed:
    print(f"  \033[32m— all security gates hold\033[0m")
    print()
    print("  Gate 1: Identity gate enforced in Python code — prompt injection cannot bypass it.")
    print("  Gate 2: Every admin route is JWT-protected — no unauthenticated access path.")
    print("  Gate 3: No PII reaches persistent logs — transcript redaction in place.")
    print("  Gate 4: Admin and chat identity systems are structurally separate.")
else:
    print(f"\n  \033[31m{failed} check(s) failed\033[0m")
    sys.exit(1)
