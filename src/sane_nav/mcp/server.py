"""Standard Model Context Protocol (MCP) JSON-RPC 2.0 stdio server.

Implements the official MCP protocol transport over standard input/output.
Enforces the strict protocol boundary requirement: standard output is reserved
exclusively for newline-delimited JSON-RPC messages; all diagnostic logging is
directed strictly to standard error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import threading
from pathlib import Path
from typing import Any

from sane_nav import __version__
from sane_nav.indexing.incremental import IncrementalSync
from sane_nav.indexing.watcher import RepoWatcher
from sane_nav.mcp.schemas import TOOL_DEFINITIONS
from sane_nav.mcp.tools import McpToolService

# Strict protocol rule: stderr only for logs, stdout ONLY for JSON-RPC messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [SANE-MCP] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("sane_nav.mcp.server")


class McpServer:
    """Core JSON-RPC MCP server managing request routing and stdio transport."""

    def __init__(self, repo_root: Path | str = "."):
        """Initializes with the target repository root and underlying tool service."""
        self.repo_root = Path(repo_root).resolve()
        self.service = McpToolService(self.repo_root)
        self._start_watcher()

    def _start_watcher(self) -> None:
        """Starts the filesystem watcher on a background thread so the index stays
        live while the agent edits files through this MCP session."""
        sync = IncrementalSync(self.service.indexer)
        watcher = RepoWatcher(self.repo_root, sync)

        def run_watcher_loop() -> None:
            try:
                asyncio.run(watcher.start() if hasattr(watcher, 'start') else asyncio.sleep(0))
            except Exception as e:
                logger.error(f"Repo watcher stopped unexpectedly: {e}")

        thread = threading.Thread(target=run_watcher_loop, name="sane-watcher", daemon=True)
        thread.start()
        logger.info(f"Started background index watcher for {self.repo_root}")

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """Processes an incoming JSON-RPC request and returns the response payload.

        Notifications return None since they expect no JSON-RPC response."""
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "sane-nav",
                        "version": __version__,
                    },
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                    "instructions": (
                        "Tool picks by what you already know: symbol/class name + want its code "
                        "-> get_symbol_code; symbol name + want call sites -> find_usages; "
                        "symbol name + want full call flow in 1 call -> explore_flow; "
                        "symbol name + want blast radius & affected tests -> analyze_impact; "
                        "file path + want exact lines with architecture context -> read_file_structural; "
                        "interface/base class + want implementors -> find_implementations; file "
                        "path + want outline -> get_skeleton; file path + want exact lines -> "
                        "read_lines; concept/keyword/filename guess -> search_semantic (matches "
                        "symbols, docs, and bare filenames; use 1-3 sharp literal tokens, not a "
                        "long phrase); directory listing -> get_file_tree; feature narrative -> "
                        "get_context.\n"
                        "explore_flow: One-shot surgical exploration of a symbol's code, callees, callers, and docs.\n"
                        "analyze_impact: Transitive blast radius (upstream callers up to depth 4, implementers, affected tests) before editing code.\n"
                        "read_file_structural: Drop-in file reader with architectural context (declared symbols, upstream callers/dependents, docs).\n"
                        "If symbol/get_symbol_code is a common name (finish, close, get), scope it: "
                        "pass kind ('method'/'field'/'class') and/or class_context (owning type), "
                        "or write 'Owner.method' directly — don't guess from a flat list of "
                        "same-named hits. find_usages groups results by file (usages_by_file) and "
                        "auto-hides test/sample/demo/benchmark matches behind a count; widen scope "
                        "only if that count looks relevant. search_semantic accepts context_symbol "
                        "(the file/symbol you just read) to rank call-graph-nearby results above "
                        "unrelated same-named hits elsewhere in the repo — set it whenever you're "
                        "mid-flow in one area, not just for the first query."
                    ),
                },
            }

        if method == "notifications/initialized":
            logger.info("Client completed initialization handshake.")
            return None

        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": TOOL_DEFINITIONS,
                },
            }

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            # Advance session turn on each tool call
            self.service.session_tracker.next_turn()

            try:
                if tool_name == "search_semantic":
                    res = self.service.search_semantic(**arguments)
                elif tool_name == "get_context":
                    res = self.service.get_context(**arguments)
                elif tool_name == "get_skeleton":
                    res = self.service.get_skeleton(**arguments)
                elif tool_name == "get_symbol_code":
                    res = self.service.get_symbol_code(**arguments)
                elif tool_name == "find_usages":
                    res = self.service.find_usages(**arguments)
                elif tool_name == "find_implementations":
                    res = self.service.find_implementations(**arguments)
                elif tool_name == "explore_flow":
                    res = self.service.explore_flow(**arguments)
                elif tool_name == "analyze_impact":
                    res = self.service.analyze_impact(**arguments)
                elif tool_name == "read_file_structural":
                    res = self.service.read_file_structural(**arguments)
                elif tool_name == "read_lines":
                    res = self.service.read_lines(**arguments)
                elif tool_name == "get_file_tree":
                    res = self.service.get_file_tree(**arguments)
                elif tool_name == "index_status":
                    res = self.service.index_status()
                else:
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32601,
                            "message": f"Method/Tool '{tool_name}' not found",
                        },
                    }

                # MCP standard tools/call response wraps content in a list
                content_text = json.dumps(res, indent=2) if isinstance(res, (dict, list)) else str(res)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": content_text,
                            }
                        ],
                        "isError": False,
                    },
                }

            except Exception as e:
                logger.exception(f"Error handling tool '{tool_name}'")
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                        "isError": True,
                    },
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Unknown method: {method}",
            },
        }

    def run_stdio(self) -> None:
        logger.info(f"Starting S.A.N.E. stdio MCP server for repository: {self.repo_root}")
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError as err:
                logger.error(f"Malformed JSON on stdin: {err}")
                continue

            response = self.handle_request(request)
            if response is not None:
                # Write to stdout strictly formatted as one JSON line
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="S.A.N.E. MCP Server")
    parser.add_argument("--repo", default=".", help="Repository root directory")
    args = parser.parse_args()

    server = McpServer(Path(args.repo))
    server.run_stdio()


if __name__ == "__main__":
    main()
