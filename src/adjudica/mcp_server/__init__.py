"""MCP server — the product surface.

This is how a bidder actually uses Adjudica: connect the server to Claude Desktop/Code
and ask questions in plain language. Claude is the client; the server just exposes tools
over the tender data. No Anthropic API key is involved — the user's own Claude
subscription drives it.

Tool logic lives in `tools.py` as plain functions so it is unit-testable without any MCP
machinery; `server.py` only registers them.
"""
