"""Standard Model Context Protocol (MCP) JSON-RPC 2.0 stdio server.

Implements the official MCP protocol transport over standard input/output.
Enforces the strict protocol boundary requirement: standard output is reserved
exclusively for newline-delimited JSON-RPC messages; all diagnostic logging is
directed strictly to standard error.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from sane_nav.mcp.schemas import TOOL_DEFINITIONS
from sane_nav.mcp.tools import McpToolService

# Strict protocol rule: stderr only for logs, stdout ONLY for JSON-RPC messages
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [SANE-MCP] %(message)s",
)
logger = logging.getLogger("sane_mcp")


class McpServer:
    """Manages JSON-RPC 2.0 lifecycle, request dispatching, and response formatting."""

    def __init__(self, repo_root: Path):
        """Initializes with the target repository root and underlying tool service."""
        self.repo_root = Path(repo_root).resolve()
        self.service = McpToolService(self.repo_root)

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """Processes an incoming JSON-RPC request and returns the response payload.

        Handles 'initialize', 'ping', 'tools/list', and 'tools/call'.
        Returns None for notifications (which do not expect a response).

        Args:
            request: Decoded JSON-RPC request object.

        Returns:
            Formatted JSON-RPC response object, or None if notification.
        """
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
                        "version": "0.1.0",
                    },
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                },
            }

        elif method == "notifications/initialized":
            logger.info("Client completed initialization handshake.")
            return None

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": TOOL_DEFINITIONS,
                },
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

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

        else:
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
    import argparse

    parser = argparse.ArgumentParser(description="S.A.N.E. MCP Server")
    parser.add_argument("--repo", default=".", help="Repository root directory")
    args = parser.parse_args()

    server = McpServer(Path(args.repo))
    server.run_stdio()


if __name__ == "__main__":
    main()
