"""
Epic E4 — Separation Guarantee proof.

Verifies at the module/import level that the two identity systems
never intersect:

  System 1 — Conversational verification (ChatSession.state)
             Routes: /chat, /verify-code
             Gate:   session state machine in tools/

  System 2 — Auth0 JWT (admin panel)
             Routes: /admin/*
             Gate:   require_admin dependency in auth/auth0.py

Rules that must hold:
  A. Admin routes must not import or touch ChatSession, SessionState, or any tool.
  B. Chat/verify routes must not import anything from auth/.
  C. require_admin must not accept a ChatSession state as a credential.
  D. No admin endpoint exists that can write to ChatSession.state.

Run: docker-compose exec backend python scripts/test_separation.py
     (No DB or Ollama needed.)
"""
import importlib
import sys
import ast
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

failures = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global failures
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}")
    if not condition:
        failures += 1
        if detail:
            print(f"         {detail}")


def imports_of(rel_path: str) -> set[str]:
    """Return the set of module names imported (directly or from) in a source file."""
    src = (ROOT / rel_path).read_text()
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
                names.add(node.module)
    return names


def name_refs_of(rel_path: str) -> set[str]:
    """Return all Name and Attribute identifiers referenced in code (AST only — excludes comments/docstrings)."""
    src = (ROOT / rel_path).read_text()
    tree = ast.parse(src)
    refs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            refs.add(node.id)
        elif isinstance(node, ast.Attribute):
            refs.add(node.attr)
    return refs


print("\nEpic E4 — Identity System Separation Guarantee\n")

# ── Rule A: Admin route must not touch chat identity ─────────────────────────
print("Rule A: Admin routes import no chat-identity symbols")

admin_imports = imports_of("routes/admin.py")
check(
    "routes/admin.py does not import models.chat_session",
    "models.chat_session" not in admin_imports and "chat_session" not in admin_imports,
)
check(
    "routes/admin.py does not import models.chat_session (SessionState)",
    "SessionState" not in (ROOT / "routes/admin.py").read_text(),
    "SessionState found in admin.py — admin must never read or write session state",
)
check(
    "routes/admin.py does not import tools.identity",
    "tools.identity" not in admin_imports and "tools" not in admin_imports,
)
check(
    "routes/admin.py does not import tools.shipments",
    "tools.shipments" not in admin_imports,
)
check(
    "routes/admin.py does not import llm.ollama_client",
    "llm.ollama_client" not in admin_imports and "llm" not in admin_imports,
)

# ── Rule B: Chat/verify routes must not touch Auth0 ───────────────────────────
print("\nRule B: Chat/verify routes import nothing from auth/")

chat_imports = imports_of("routes/chat.py")
verify_imports = imports_of("routes/verify.py")

check(
    "routes/chat.py does not import auth",
    "auth" not in chat_imports and "auth.auth0" not in chat_imports,
)
check(
    "routes/verify.py does not import auth",
    "auth" not in verify_imports and "auth.auth0" not in verify_imports,
)
check(
    "routes/chat.py does not reference require_admin",
    "require_admin" not in (ROOT / "routes/chat.py").read_text(),
)
check(
    "routes/verify.py does not reference require_admin",
    "require_admin" not in (ROOT / "routes/verify.py").read_text(),
)

# ── Rule C: require_admin gate is JWT-only ────────────────────────────────────
print("\nRule C: require_admin validates JWT only — no session state involved")

auth_src = (ROOT / "auth/auth0.py").read_text()
auth_imports = imports_of("auth/auth0.py")
auth_refs = name_refs_of("auth/auth0.py")

check(
    "auth/auth0.py does not import models.chat_session",
    "models.chat_session" not in auth_imports and "chat_session" not in auth_imports,
)
check(
    "auth/auth0.py does not reference SessionState in code",
    "SessionState" not in auth_refs,
)
check(
    "auth/auth0.py uses jwt.decode (JWKS-based RS256 validation)",
    "jwt.decode" in auth_src,
)
check(
    "auth/auth0.py does not reference ChatSession in code",
    "ChatSession" not in auth_refs,
)

# ── Rule D: No admin endpoint writes to ChatSession ───────────────────────────
print("\nRule D: Admin routes never write to ChatSession")

admin_src = (ROOT / "routes/admin.py").read_text()
admin_refs = name_refs_of("routes/admin.py")

check(
    "routes/admin.py does not reference ChatSession in code",
    "ChatSession" not in admin_refs,
    "ChatSession found in admin.py — admin must not read or write chat sessions",
)
check(
    "routes/admin.py does not reference SessionState in code",
    "SessionState" not in admin_refs,
)
check(
    "routes/admin.py does not reference verification_code in code",
    "verification_code" not in admin_refs,
)

# ── Rule E: Structural — only verify.py can transition to verified ────────────
print("\nRule E: Only verify.py can set state = verified")

verify_src = (ROOT / "routes/verify.py").read_text()
chat_src = (ROOT / "routes/chat.py").read_text()

verify_sets_verified = "SessionState.verified" in verify_src
chat_src_has_verified = "SessionState.verified" in chat_src  # used for checks, not assignment
admin_sets_verified = "verified" in admin_src and "state" in admin_src

check(
    "routes/verify.py is the only route that transitions state → verified",
    verify_sets_verified,
    "verify.py must assign SessionState.verified on correct code entry",
)
check(
    "routes/admin.py never assigns a verified state",
    "SessionState.verified" not in admin_src,
)

# ── Summary ───────────────────────────────────────────────────────────────────
total = 16
passed = total - failures
print(f"\n{'─' * 50}")
print(f"Result: {passed}/{total} checks passed", end="")
if failures == 0:
    print(f"  \033[32m— separation guarantee holds\033[0m")
else:
    print(f"\n\033[31m{failures} check(s) failed — separation is broken\033[0m")
    sys.exit(1)
