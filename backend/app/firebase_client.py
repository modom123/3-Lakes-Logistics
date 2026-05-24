"""Firebase Admin SDK initialization — singleton pattern."""
from __future__ import annotations

import os
import json
from pathlib import Path

_app = None

def get_firebase_app():
    """Return initialized Firebase app, or None if credentials not found."""
    global _app
    if _app is not None:
        return _app

    try:
        import firebase_admin
        from firebase_admin import credentials

        # Already initialized
        if firebase_admin._apps:
            _app = firebase_admin.get_app()
            return _app

        # Option 1: serviceAccountKey.json file next to backend/
        key_path = Path(__file__).parent.parent.parent / "serviceAccountKey.json"
        if not key_path.exists():
            # Option 2: FIREBASE_SERVICE_ACCOUNT env var (JSON string)
            sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
            if sa_json:
                sa_dict = json.loads(sa_json)
                cred = credentials.Certificate(sa_dict)
            else:
                return None
        else:
            cred = credentials.Certificate(str(key_path))

        _app = firebase_admin.initialize_app(cred)
        return _app

    except ImportError:
        return None
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Firebase init failed: %s", e)
        return None
