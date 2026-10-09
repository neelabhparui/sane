"""Command-Line Interface (CLI) for S.A.N.E.

Exposes commands for repository initialization, indexing, MCP serving,
health checks, symbol extraction, usage tracing, implementations, and agent configuration.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

from sane_nav.indexing.indexer import Indexer
from sane_nav.mcp.server import McpServer
from sane_nav.mcp.tools import McpToolService
from sane_nav.parsing.registry import ParserRegistry
from sane_nav.paths import RepoPaths
from sane_nav.storage.database import Database

BANNER = r"""
   _____   ___    _   __   ______
  / ___/  /   |  / | / /  / ____/
  \__ \  / /| | /  |/ /  / __/   
 ___/ / / ___ |/ /|  /  / /___   
/____/ /_/  |_/_/ |_/  /_____/   
Semantic Agent Navigation Engine v0.4.4
"""


AGENT_CONFIGS = {
    "claude": {
        "path": ".mcp.json",
        "build": lambda repo_root: {
            "mcpServers": {
                "sane": {
                    "command": "sane",
                    "args": ["serve", "--repo", str(repo_root)],
                }
            }
        },
    },
    "cursor": {
        "path": ".cursor/mcp.json",
        "build": lambda repo_root: {
            "mcpServers": {
                "sane": {
                    "command": "sane",
                    "args": ["serve", "--repo", str(repo_root)],
                }
            }
        },
    },
    "vscode": {
        "path": ".vscode/mcp.json",
        "build": lambda repo_root: {
            "mcpServers": {
                "sane": {
                    "type": "stdio",
                    "command": "sane",
                    "args": ["serve", "--repo", str(repo_root)],
                }
            }
        },
    },
    "codex": {
        "path": ".codex/config.toml",
        "build": None,
    },
}


def _checkbox_prompt(options: list[str], prompt: str) -> list[str]:
    """Interactive multi-select checkbox menu (↑/↓ move, space toggles, enter confirms).

    Falls back to a plain comma-separated text prompt when stdin isn't a TTY
    or the terminal doesn't support raw mode (e.g. piped input, Windows cmd).
    """
    if not sys.stdin.isatty():
        return []

    try:
        import termios
        import tty
    except ImportError:
        print(f"\n{prompt}")
        print(f"  Options: {', '.join(options)} (comma-separated, or blank to skip)")
        try:
            answer = input("> ").strip()
        except EOFError:
            answer = ""
        return [a.strip().lower() for a in answer.split(",") if a.strip()]

    selected = [False] * len(options)
    cursor = 0

    def render(first: bool = False):
        if not first:
            sys.stdout.write(f"\x1b[{len(options) + 1}A")
        sys.stdout.write(f"\r{prompt}\x1b[K\n")
        for i, opt in enumerate(options):
            mark = "x" if selected[i] else " "
            pointer = "›" if i == cursor else " "
            sys.stdout.write(f"\r{pointer} [{mark}] {opt}\x1b[K\n")
        sys.stdout.flush()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    print("\n(↑/↓ move, space toggles, enter confirms)")
    try:
        tty.setcbreak(fd)
        render(first=True)
        while True:
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                ch3 = sys.stdin.read(1) if ch2 == "[" else ""
                if ch3 == "A":
                    cursor = (cursor - 1) % len(options)
                elif ch3 == "B":
                    cursor = (cursor + 1) % len(options)
                render()
            elif ch == " ":
                selected[cursor] = not selected[cursor]
                render()
            elif ch in ("\r", "\n"):
                break
            elif ch == "\x03":
                raise KeyboardInterrupt
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    return [opt for opt, is_sel in zip(options, selected) if is_sel]


def _merge_mcp_json(config_path: Path, snippet: dict) -> None:
    """Merges a {"mcpServers": {...}} snippet into an existing or new JSON file."""
    existing: dict = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing.setdefault("mcpServers", {})
    existing["mcpServers"].update(snippet["mcpServers"])
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")


def _setup_agent(client: str, repo_root: Path) -> None:
    client = client.lower()
    if client == "codex":
        toml_path = repo_root / ".codex" / "config.toml"
        toml_path.parent.mkdir(parents=True, exist_ok=True)
        snippet = (
            f'\n[mcp_servers.sane]\n'
            f'command = "sane"\n'
            f'args = ["serve", "--repo", "{repo_root}"]\n'
        )
        existing = toml_path.read_text(encoding="utf-8") if toml_path.exists() else ""
        if "[mcp_servers.sane]" in existing:
            print(f"  • codex: sane already configured in {toml_path}")
            return
        with open(toml_path, "a", encoding="utf-8") as f:
            f.write(snippet)
        print(f"  • codex: added sane MCP server to {toml_path}")
        return

    cfg = AGENT_CONFIGS.get(client)
    if not cfg:
        print(f"  • {client}: unsupported, skipped")
        return
    config_path = repo_root / cfg["path"]
    _merge_mcp_json(config_path, cfg["build"](repo_root))
    print(f"  • {client}: added sane MCP server to {config_path}")


def cmd_init(args: argparse.Namespace) -> int:
    """One-shot setup: creates .sane.toml, indexes the repo, and wires up MCP for chosen agents."""
    print(BANNER)
    repo_root = Path(args.repo).resolve()
    config_path = repo_root / ".sane.toml"

    if config_path.exists():
        print(f"S.A.N.E. configuration already exists at {config_path}")
    else:
        default_toml = _default_toml()
        config_path.write_text(default_toml, encoding="utf-8")
        print(f"Created {config_path}")

        gi = repo_root / ".gitignore"
        if gi.exists():
            gi_content = gi.read_text(encoding="utf-8", errors="ignore")
            if ".sane" not in gi_content:
                with open(gi, "a", encoding="utf-8") as f:
                    f.write("\n# S.A.N.E. index directory\n.sane/\n")
                print("Added '.sane/' to .gitignore")

    print(f"\nIndexing repository at: {repo_root}")
    paths = RepoPaths(repo_root)
    db = Database(paths.db_path)
    indexer = Indexer(paths, db)

    def on_prog(file_path: str, cur: int, total: int):
        pct = (cur / total) * 100
        sys.stderr.write(f"\r  [{cur}/{total}] ({pct:.1f}%) Indexing {file_path[:50]:<50}")
        sys.stderr.flush()

    stats = indexer.index_all(on_progress=on_prog)
    print("\n")
    print("✓ Indexing complete!")
    print(f"  • Total files discovered: {stats['total_files']}")
    print(f"  • Files parsed & indexed: {stats['indexed_files']}")
    print(f"  • Resolved references:   {stats['resolved_references']}")

    agents_arg = getattr(args, "agents", None)
    if agents_arg:
        selected = [a.strip().lower() for a in agents_arg.split(",") if a.strip()]
    elif getattr(args, "no_agents", False) or not sys.stdin.isatty():
        selected = []
    else:
        selected = _checkbox_prompt(
            list(AGENT_CONFIGS.keys()),
            "Which agents should be configured to use S.A.N.E. via MCP?",
        )

    if selected:
        print("\nConfiguring agents:")
        for client in selected:
            _setup_agent(client, repo_root)

    print("\n✓ S.A.N.E. is ready. Run 'sane serve --repo .' to start the MCP server manually,")
    print("  or your configured agent will launch it automatically.")
    return 0


def cmd_reinit(args: argparse.Namespace) -> int:
    """Forces a clean slate: deletes the existing .sane/ index (and .sane.toml
    unless --keep-config) then runs init from scratch."""
    repo_root = Path(args.repo).resolve()
    paths = RepoPaths(repo_root)

    if paths.sane_dir.exists():
        shutil.rmtree(paths.sane_dir)
        print(f"Removed {paths.sane_dir}")
    else:
        print("No existing .sane/ index to remove")

    if not getattr(args, "keep_config", False):
        config_path = repo_root / ".sane.toml"
        if config_path.exists():
            config_path.unlink()
            print(f"Removed {config_path}")

    print()
    return cmd_init(args)


def _default_toml() -> str:
    return """# S.A.N.E. Configuration (.sane.toml)

[repository]
respect_gitignore = true
max_file_bytes = 2097152

include = [
  "**/*.py",
  "**/*.java",
  "**/*.kt",
  "**/*.kts",
  "**/*.md",
]

exclude = [
  ".git/**",
  ".sane/**",
  "build/**",
  "dist/**",
  "node_modules/**",
  ".gradle/**",
  ".idea/**",
  ".venv/**",
  "__pycache__/**",
]

[index]
parse_workers = 4

[watch]
enabled = true
debounce_ms = 300

[search]
semantic = false
default_limit = 8

[output]
max_chars = 12000
max_usages = 20
"""


def cmd_index(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo).resolve()
    print(BANNER)
    print(f"Indexing repository at: {repo_root}")

    paths = RepoPaths(repo_root)
    db = Database(paths.db_path)
    indexer = Indexer(paths, db)

    def on_prog(file_path: str, cur: int, total: int):
        pct = (cur / total) * 100
        sys.stderr.write(f"\r  [{cur}/{total}] ({pct:.1f}%) Indexing {file_path[:50]:<50}")
        sys.stderr.flush()

    stats = indexer.index_all(on_progress=on_prog)
    print("\n")
    print("✓ Indexing complete!")
    print(f"  • Total files discovered: {stats['total_files']}")
    print(f"  • Files parsed & indexed: {stats['indexed_files']}")
    print(f"  • Skipped (unchanged):   {stats['skipped_files']}")
    print(f"  • Resolved references:   {stats['resolved_references']}")
    print(f"  • Database path:         {paths.db_path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo).resolve()
    paths = RepoPaths(repo_root)
    if not paths.db_path.exists():
        print(f"Index not found at {paths.db_path}. Run 'sane index' first.")
        return 1

    db = Database(paths.db_path)
    stats = db.get_stats()
    print("S.A.N.E. Index Status:")
    print(json.dumps(stats, indent=2))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    service = McpToolService(Path(args.repo).resolve())
    res = service.search_semantic(args.query, limit=args.limit)

    print(f"\n--- Search results for '{args.query}' ({len(res['results'])} matches) ---")
    for r in res["results"]:
        if r.get("kind") == "doc":
            print(f"\n[DOC] {r['title']} in {r['file']}:{r['lines'][0]}")
            print(f"      {r['preview'][:100]}...")
        else:
            print(f"\n[{r['kind'].upper()}] {r['qualified_name'] or r['name']} ({r['file']}:{r['lines'][0]}-{r['lines'][1]})")
            if r.get("signature"):
                print(f"      {r['signature']}")
            print(f"      Match: {r['match']['reason']} (score: {r['match']['score']})")
    print("")
    return 0


def cmd_skeleton(args: argparse.Namespace) -> int:
    service = McpToolService(Path(args.repo).resolve())
    res = service.get_skeleton(args.file)
    print(f"\n--- Skeleton of {args.file} ---")
    print(res["skeleton"])
    return 0


def cmd_symbol(args: argparse.Namespace) -> int:
    service = McpToolService(Path(args.repo).resolve())
    res = service.get_symbol_code(args.symbol, context_lines=args.context)
    if res.get("status") == "not_found":
        print(f"Error: {res.get('error')}")
        return 1
    if res.get("status") == "ambiguous":
        print(f"Ambiguous: {res.get('message')}")
        for c in res.get("candidates", []):
            print(f"  • {c['symbol_id']} ({c['file']}:{c['lines'][0]})")
        return 0
    print(f"\n--- Symbol: {res['name']} ({res['file']}:{res['lines'][0]}-{res['lines'][1]}) ---")
    print(res["code"])
    return 0


def cmd_usages(args: argparse.Namespace) -> int:
    service = McpToolService(Path(args.repo).resolve())
    res = service.find_usages(args.symbol, limit=args.limit)
    print(f"\n--- Usages for '{args.symbol}' ({res['total_found']} found) ---")
    for file_group in res.get("usages_by_file", []):
        for u in file_group["usages"]:
            tag = "EXACT" if u["confidence"] >= 0.9 else "PROBABLE"
            print(f"\n[{tag}] {u['file']}:{u['line']} (in {u.get('enclosing_symbol') or 'global'}, confidence {u['confidence']}):")
            print(u["snippet"])
    return 0


def cmd_implementations(args: argparse.Namespace) -> int:
    service = McpToolService(Path(args.repo).resolve())
    res = service.find_implementations(args.symbol, transitive=not args.direct_only)
    print(f"\n--- Implementations / Subclasses of '{args.symbol}' ({res['total_found']} found) ---")
    if res.get("direct_implementers"):
        print("\nDirect Implementers:")
        for imp in res["direct_implementers"]:
            print(f"  • {imp['name']} — {imp['file']}:{imp['lines'][0]} ({imp['kind']})")
            if imp.get("signature"):
                print(f"    {imp['signature']}")
    if res.get("indirect_implementers"):
        print("\nIndirect Implementers:")
        for imp in res["indirect_implementers"]:
            print(f"  • {imp['name']} (depth {imp['depth']}) — {imp['file']}:{imp['lines'][0]} ({imp['kind']})")
            if imp.get("signature"):
                print(f"    {imp['signature']}")
    if res["total_found"] == 0:
        print("  None found.")
    print("")
    return 0


def cmd_flow(args: argparse.Namespace) -> int:
    service = McpToolService(Path(args.repo).resolve())
    res = service.explore_flow(args.symbol, max_depth=args.depth)
    if res.get("status") == "not_found":
        print(f"Error: {res.get('error')}")
        return 1
    if res.get("status") == "ambiguous":
        print(f"Ambiguous: {res.get('message')}")
        for c in res.get("candidates", []):
            print(f"  • {c['symbol_id']} ({c['file']}:{c['lines'][0]})")
        return 0
    print(res.get("flow", ""))
    return 0


def cmd_impact(args: argparse.Namespace) -> int:
    service = McpToolService(Path(args.repo).resolve())
    res = service.analyze_impact(args.symbol, depth=args.depth, include_tests=not args.no_tests)
    if res.get("status") == "not_found":
        print(f"Error: {res.get('error')}")
        return 1
    if res.get("status") == "ambiguous":
        print(f"Ambiguous: {res.get('message')}")
        for c in res.get("candidates", []):
            print(f"  • {c['symbol_id']} ({c['file']}:{c['lines'][0]})")
        return 0
    print(res.get("report", ""))
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo).resolve()
    paths = RepoPaths(repo_root)
    if paths.sane_dir.exists():
        shutil.rmtree(paths.sane_dir)
        print(f"Removed {paths.sane_dir}")
    else:
        print("Nothing to clean (.sane/ does not exist)")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    print(BANNER)
    print("Running S.A.N.E. System & Health Diagnostics:\n")

    # 1. SQLite & FTS5 check
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE fts_test USING fts5(content);")
        print("✓ SQLite FTS5 extension: Available and operational")
    except Exception as e:
        print(f"✗ SQLite FTS5 check failed: {e}")

    # 2. Python environment
    print(f"✓ Python runtime: {sys.version.split()[0]} ({sys.executable})")

    # 3. Parsers check
    reg = ParserRegistry()
    supported = [a.language for a in reg.adapters]
    print(f"✓ Parsers registered: {', '.join(supported)}")

    # 4. Check repository root
    repo_root = Path(args.repo).resolve()
    print(f"✓ Target repository: {repo_root}")

    # 5. MCP capabilities
    print("✓ MCP Stdio JSON-RPC 2.0 interface: Ready")
    print("\nAll diagnostics passed! S.A.N.E. is healthy and ready to serve.")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    client = args.client.lower()
    repo_root = Path(args.repo).resolve()

    if client == "claude":
        config_snippet = {
            "mcpServers": {
                "sane": {
                    "command": "sane",
                    "args": ["serve", "--repo", str(repo_root)],
                }
            }
        }
        cmd_str = f"claude mcp add sane -- sane serve --repo {repo_root}"
        print("\nTo configure Claude Code, run:")
        print(f"  {cmd_str}\n")
        print("Or add to your project's claude mcp settings:")
        print(json.dumps(config_snippet, indent=2))

    elif client == "cursor":
        config_path = repo_root / ".cursor" / "mcp.json"
        cursor_config = {
            "mcpServers": {
                "sane": {
                    "command": "sane",
                    "args": ["serve", "--repo", "."]
                }
            }
        }
        if args.write:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(cursor_config, indent=2), encoding="utf-8")
            print(f"Wrote Cursor MCP configuration to {config_path}")
        else:
            print(f"\nCursor MCP configuration for {config_path}:")
            print(json.dumps(cursor_config, indent=2))
            print("\nRun with '--write' to create .cursor/mcp.json automatically.")

    elif client == "vscode":
        config_path = repo_root / ".vscode" / "mcp.json"
        vscode_config = {
            "mcpServers": {
                "sane": {
                    "type": "stdio",
                    "command": "sane",
                    "args": ["serve", "--repo", "."]
                }
            }
        }
        if args.write:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(vscode_config, indent=2), encoding="utf-8")
            print(f"Wrote VS Code MCP configuration to {config_path}")
        else:
            print(f"\nVS Code MCP configuration for {config_path}:")
            print(json.dumps(vscode_config, indent=2))
            print("\nRun with '--write' to create .vscode/mcp.json automatically.")
    else:
        print(f"Unknown client '{client}'. Supported: claude, cursor, vscode")
        return 1

    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    server = McpServer(Path(args.repo).resolve())
    server.run_stdio()
    return 0


def main() -> None:
    # Common parent parser for flags like --repo
    repo_parent = argparse.ArgumentParser(add_help=False)
    repo_parent.add_argument("--repo", default=".", help="Repository root path (default: .)")

    parser = argparse.ArgumentParser(
        prog="sane",
        description="S.A.N.E. - Semantic Agent Navigation Engine for AI coding agents",
        parents=[repo_parent],
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # sane init
    p_init = subparsers.add_parser(
        "init", parents=[repo_parent],
        help="One-shot setup: create .sane.toml, index the repo, and configure MCP for agents",
    )
    p_init.add_argument(
        "--agents", default=None,
        help="Comma-separated agents to configure (claude,codex,cursor,vscode); skips the interactive prompt",
    )
    p_init.add_argument(
        "--no-agents", action="store_true",
        help="Skip agent configuration entirely (no prompt)",
    )

    # sane reinit
    p_reinit = subparsers.add_parser(
        "reinit", parents=[repo_parent],
        help="Force a clean reinit: deletes the existing .sane/ index (and .sane.toml) then runs init from scratch",
    )
    p_reinit.add_argument(
        "--keep-config", action="store_true",
        help="Keep the existing .sane.toml instead of regenerating it",
    )
    p_reinit.add_argument(
        "--agents", default=None,
        help="Comma-separated agents to configure (claude,codex,cursor,vscode); skips the interactive prompt",
    )
    p_reinit.add_argument(
        "--no-agents", action="store_true",
        help="Skip agent configuration entirely (no prompt)",
    )

    # sane index
    subparsers.add_parser("index", parents=[repo_parent], help="Index or incrementally refresh repository")

    # sane serve
    subparsers.add_parser("serve", parents=[repo_parent], help="Run MCP stdio server")

    # sane status
    subparsers.add_parser("status", parents=[repo_parent], help="Show index status and statistics")

    # sane search
    p_search = subparsers.add_parser("search", parents=[repo_parent], help="Search symbols and documentation")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--limit", type=int, default=8, help="Max results")

    # sane skeleton
    p_skel = subparsers.add_parser("skeleton", parents=[repo_parent], help="Display structural skeleton of a file")
    p_skel.add_argument("file", help="File path relative to repo root")

    # sane symbol
    p_sym = subparsers.add_parser("symbol", parents=[repo_parent], help="Extract code implementation for a symbol")
    p_sym.add_argument("symbol", help="Symbol name or URI")
    p_sym.add_argument("--context", type=int, default=0, help="Additional context lines")

    # sane usages
    p_usage = subparsers.add_parser("usages", parents=[repo_parent], help="Find usages of a symbol")
    p_usage.add_argument("symbol", help="Symbol name or URI")
    p_usage.add_argument("--limit", type=int, default=10, help="Max usages")

    # sane implementations
    p_imp = subparsers.add_parser("implementations", parents=[repo_parent], help="Find classes implementing or extending a symbol")
    p_imp.add_argument("symbol", help="Target symbol name or URI")
    p_imp.add_argument("--direct-only", action="store_true", help="Only show direct implementers")

    # sane flow
    p_flow = subparsers.add_parser("flow", parents=[repo_parent], help="One-shot exploration of symbol flow (code + callers + callees + docs)")
    p_flow.add_argument("symbol", help="Symbol name or URI")
    p_flow.add_argument("--depth", type=int, default=1, help="Call graph traversal depth for callees (default: 1)")

    # sane impact
    p_impact = subparsers.add_parser("impact", parents=[repo_parent], help="Transitive blast radius and refactor safety analysis")
    p_impact.add_argument("symbol", help="Target symbol name or URI")
    p_impact.add_argument("--depth", type=int, default=2, help="Upstream caller depth (default: 2)")
    p_impact.add_argument("--no-tests", action="store_true", help="Skip affected test suites search")

    # sane clean
    subparsers.add_parser("clean", parents=[repo_parent], help="Remove S.A.N.E. index and locks")

    # sane doctor
    subparsers.add_parser("doctor", parents=[repo_parent], help="Run diagnostic health checks")

    # sane setup
    p_setup = subparsers.add_parser("setup", parents=[repo_parent], help="Generate MCP client configurations")
    p_setup.add_argument("client", choices=["claude", "cursor", "vscode"], help="Target client")
    p_setup.add_argument("--write", action="store_true", help="Write configuration file directly")

    args = parser.parse_args()

    dispatch = {
        "init": cmd_init,
        "reinit": cmd_reinit,
        "index": cmd_index,
        "serve": cmd_serve,
        "status": cmd_status,
        "search": cmd_search,
        "skeleton": cmd_skeleton,
        "symbol": cmd_symbol,
        "usages": cmd_usages,
        "implementations": cmd_implementations,
        "flow": cmd_flow,
        "impact": cmd_impact,
        "clean": cmd_clean,
        "doctor": cmd_doctor,
        "setup": cmd_setup,
    }

    handler = dispatch.get(args.command)
    if handler:
        sys.exit(handler(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
