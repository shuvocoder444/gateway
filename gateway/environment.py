"""Load deployment-only environment values from a private file when present."""

import os
from pathlib import Path


DEFAULT_ENV_FILE = Path('/home/webkoders/.config/payment.webkoders.com/environment')


def load_environment():
    env_file = Path(os.environ.get('DJANGO_ENV_FILE', DEFAULT_ENV_FILE))
    try:
        lines = env_file.read_text(encoding='utf-8').splitlines()
    except FileNotFoundError:
        return

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1)
        name = name.strip()
        value = value.strip()
        if name and name.replace('_', '').isalnum():
            os.environ[name] = value
