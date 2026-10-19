from __future__ import annotations
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .providers.betpawa import BetPawaFeed
from .predictor import build_prediction
from .db import save_public_predictions, list_predictions

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend" / "index.html"

app = FastAPI(title="BetPawa Predictor", version="0.2.0")
feed = BetPawaFeed()


@app.get("/")
def home():
    return FileResponse(FRONTEND)


@app.get("/api/status")
def status():
    return {
        "app": "BetPawa Predictor",
        "version": "0.2.0",
        "rules_public": False,
        "mode": "on-demand recent verification",
    }


@app.post("/api/predict")
def predict():
    try:
        context = feed.prediction_context()
        result = build_prediction(context)
        # Feed/debug internals are not returned to the public dashboard.
        result["feed_mode"] = context.get("feed_mode")
        save_public_predictions(result)
        return result
    except Exception as e:
        raise HTTPException(502, str(e))


@app.get("/api/predictions")
def predictions(limit: int = 50):
    return list_predictions(max(1, min(limit, 200)))


@app.get("/api/diagnose")
def diagnose():
    # Troubleshooting only. No strategy IDs/names/thresholds are exposed.
    return feed.diagnose()
