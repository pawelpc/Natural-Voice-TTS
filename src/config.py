"""Persistent JSON configuration for Natural Voice TTS."""

import json
import os
import sys
import logging
import threading

logger = logging.getLogger(__name__)

# Application base directory (frozen exe or source tree)
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

# Config file location (always in user APPDATA, not the install dir)
CONFIG_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'NaturalVoiceTTS')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')

DEFAULTS = {
    'voice': 'af_heart',
    'speed': 1.0,
}

# All available Kokoro English voices
VOICES = {
    'American Female': [
        'af_alloy', 'af_aoede', 'af_bella', 'af_heart', 'af_jessica',
        'af_kore', 'af_nicole', 'af_nova', 'af_river', 'af_sarah', 'af_sky',
    ],
    'American Male': [
        'am_adam', 'am_echo', 'am_eric', 'am_fenrir', 'am_liam',
        'am_michael', 'am_onyx', 'am_puck',
    ],
    'British Female': ['bf_alice', 'bf_emma', 'bf_isabella', 'bf_lily'],
    'British Male': ['bm_daniel', 'bm_fable', 'bm_george', 'bm_lewis'],
}

SPEED_OPTIONS = [0.75, 1.0, 1.25, 1.5, 2.0]

_lock = threading.Lock()
_config: dict | None = None


def load() -> dict:
    """Load config from disk. Creates default config if missing."""
    global _config
    with _lock:
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r') as f:
                    _config = json.load(f)
                # Fill in any missing keys with defaults
                for key, value in DEFAULTS.items():
                    _config.setdefault(key, value)
                logger.info("Config loaded from %s", CONFIG_PATH)
            except (json.JSONDecodeError, OSError):
                logger.warning("Config file corrupted, using defaults")
                _config = dict(DEFAULTS)
                _save_locked()
        else:
            _config = dict(DEFAULTS)
            _save_locked()
            logger.info("Created default config at %s", CONFIG_PATH)
        return dict(_config)


def _save_locked() -> None:
    """Save config to disk (caller must hold _lock)."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        json.dump(_config, f, indent=2)


def save() -> None:
    """Save current config to disk."""
    with _lock:
        if _config is not None:
            _save_locked()
            logger.info("Config saved")


def get(key: str):
    """Get a config value. Loads config if not yet loaded."""
    if _config is None:
        load()
    with _lock:
        return _config.get(key, DEFAULTS.get(key))


def set(key: str, value) -> None:
    """Set a config value and persist to disk."""
    if _config is None:
        load()
    with _lock:
        _config[key] = value
        _save_locked()
    logger.info("Config: %s = %s", key, value)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    cfg = load()
    logger.info("Config: %s", cfg)
    logger.info("Config path: %s", CONFIG_PATH)

    # Test set/get
    current_voice = get('voice')
    logger.info("Current voice: %s", current_voice)

    logger.info("Available voices:")
    for category, voices in VOICES.items():
        logger.info("  %s: %s", category, ', '.join(voices))
