"""Resolve an explicit runtime root without walking into unrelated ancestors."""
import os
from pathlib import Path
import sys


def game_root():
    configured = os.environ.get('PSOBB_GAME_ROOT')
    if configured:
        root = Path(configured).expanduser().resolve()
        if not root.is_dir():
            raise ValueError('PSOBB_GAME_ROOT must point to an existing directory')
        return root
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]
