"""Configure (or remove) the Natural Voice TTS MCP server entry in Claude Desktop.

Usage:
    python install_config.py            Add/update the MCP server entry
    python install_config.py --remove   Remove the MCP server entry

This script locates its own directory to build the correct path to server.py,
then patches %APPDATA%\\Claude\\claude_desktop_config.json accordingly.
"""

import argparse
import json
import os
import sys

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MCP_SERVER_KEY = 'natural-voice-tts'

CONFIG_DIR = os.path.join(os.environ.get('APPDATA', ''), 'Claude')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'claude_desktop_config.json')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _server_py_path() -> str:
    """Return the absolute path to server.py next to this script."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, 'server.py')


def _run_server_bat_path() -> str:
    """Return the absolute path to run_server.bat next to this script."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, 'run_server.bat')


def _load_config() -> dict:
    """Load the existing Claude Desktop config, or return an empty dict."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_config(config: dict) -> None:
    """Write the config back to disk with readable formatting."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def add_entry() -> None:
    """Add or update the natural-voice-tts MCP server entry."""
    if not os.path.isdir(CONFIG_DIR):
        print(f"Claude Desktop config directory not found: {CONFIG_DIR}")
        print("Is Claude Desktop installed? Install it from https://claude.ai/download")
        print("If Claude Desktop is installed but this path doesn't exist, "
              "launch it once to create the default config directory.")
        sys.exit(1)

    server_py = _server_py_path()
    run_bat = _run_server_bat_path()

    if not os.path.exists(server_py):
        print(f"ERROR: server.py not found at {server_py}")
        print("The MCP server files may not be installed correctly.")
        sys.exit(1)

    config = _load_config()

    if 'mcpServers' not in config:
        config['mcpServers'] = {}

    # Use cmd.exe /c run_server.bat to work with Microsoft Store Python
    config['mcpServers'][MCP_SERVER_KEY] = {
        'command': 'C:\\Windows\\System32\\cmd.exe',
        'args': ['/c', run_bat],
    }

    _save_config(config)

    print("=" * 60)
    print("  Claude Desktop configured for Natural Voice TTS")
    print("=" * 60)
    print()
    print(f"  Config file : {CONFIG_FILE}")
    print(f"  Server path : {server_py}")
    print(f"  Launch via  : cmd.exe /c {run_bat}")
    print()
    print("  IMPORTANT: Restart Claude Desktop for changes to take effect.")
    print("             (Quit from tray icon, then relaunch.)")
    print()


def remove_entry() -> None:
    """Remove the natural-voice-tts MCP server entry."""
    if not os.path.exists(CONFIG_FILE):
        print("Claude Desktop config file not found — nothing to remove.")
        return

    config = _load_config()

    if 'mcpServers' not in config or MCP_SERVER_KEY not in config['mcpServers']:
        print(f"No '{MCP_SERVER_KEY}' entry found in config — nothing to remove.")
        return

    del config['mcpServers'][MCP_SERVER_KEY]

    # Clean up empty mcpServers dict
    if not config['mcpServers']:
        del config['mcpServers']

    _save_config(config)

    print(f"Removed '{MCP_SERVER_KEY}' from {CONFIG_FILE}")
    print("Restart Claude Desktop for changes to take effect.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the config helper."""
    parser = argparse.ArgumentParser(
        description='Configure Claude Desktop for Natural Voice TTS MCP server.',
    )
    parser.add_argument(
        '--remove',
        action='store_true',
        help='Remove the Natural Voice TTS entry from Claude Desktop config.',
    )
    args = parser.parse_args()

    if args.remove:
        remove_entry()
    else:
        add_entry()


if __name__ == '__main__':
    main()
