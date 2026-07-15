from __future__ import annotations

from pathlib import Path

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8100,
        reload=True,
        app_dir=str(Path(__file__).resolve().parent),
    )
