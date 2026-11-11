"""Refuse unsafe Railway starts before subscriber and payment data is durable.

Railway provides RAILWAY_VOLUME_MOUNT_PATH at runtime for attached volumes.
This check runs as the Docker container start command after volumes are mounted.
Local Docker development and other hosting providers remain unaffected.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def validate_railway_environment(environ=None):
    env = environ if environ is not None else os.environ
    if not env.get("RAILWAY_PROJECT_ID"):
        return
    dbpath = Path(env.get("PREDICTOR_DB_PATH", "/var/data/predictor.db"))
    volume = env.get("RAILWAY_VOLUME_MOUNT_PATH", "").rstrip("/")
    if volume != "/var/data" or dbpath != Path("/var/data/predictor.db"):
        raise RuntimeError(
            "Railway requires an attached persistent volume mounted at /var/data "
            "and PREDICTOR_DB_PATH=/var/data/predictor.db. Attach a volume "
            "in Railway before starting the predictor."
        )
    if not Path(volume).is_dir() or not os.access(volume, os.W_OK):
        raise RuntimeError("Railway persistent volume /var/data is not writable.")
    password = env.get("PREDICTOR_ADMIN_PASSWORD", "")
    if len(password) < 12:
        raise RuntimeError(
            "Set PREDICTOR_ADMIN_PASSWORD in Railway Variables to a strong "
            "private password of at least 12 characters."
        )


def main():
    try:
        validate_railway_environment()
    except RuntimeError as exc:
        print(f"DEPLOYMENT BLOCKED: {exc}", file=sys.stderr)
        return 1
    print("Deployment preflight succeeded.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
