"""
Web routes for thefeedback feature.

webapp.py includes this router with two lines:

    from feedback_routes import router as feedback_router
    app.include_router(feedback_router)

Routes (all under /api/feedback):
    GET  /classes              the class list for the drop-down
    GET  /frame/{stem}?t=<ms>  the clean frame as a JPEG (t is only used for videos)
    POST /save                 save the drawn boxes as a feedback sample
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

import feedback_core

router = APIRouter(prefix="/api/feedback")


class BoxIn(BaseModel):
    class_name: str
    # Corners in pixels of the frame returned by /frame.
    x_min: float
    y_min: float
    x_max: float
    y_max: float


class SaveIn(BaseModel):
    name: str
    t_ms: Optional[int] = None
    boxes: List[BoxIn]


@router.get("/classes")
def get_classes():
    return [
        {"name": class_name, "model": feedback_core.FEEDBACK_CLASS_TO_MODEL[class_name]}
        for class_name in feedback_core.FEEDBACK_CLASS_NAMES
    ]


@router.get("/frame/{name}")
def get_frame(name: str, t: Optional[int] = None):
    try:
        frame, is_clean = feedback_core.load_frame(name, t)
    except ValueError:
        raise HTTPException(status_code=404, detail="Error: File not found")

    if frame is None:
        raise HTTPException(
            status_code=404,
            detail="Error: Could not read a frame for this file. "
            "If the original upload was cleared, upload it again.",
        )

    height, width = frame.shape[:2]
    return Response(
        content=feedback_core.encode_jpeg(frame),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store",
            "X-Frame-Width": str(width),
            "X-Frame-Height": str(height),
            "X-Frame-Clean": "true" if is_clean else "false",
            "Access-Control-Expose-Headers": "X-Frame-Width, X-Frame-Height, X-Frame-Clean",
        },
    )


@router.post("/save")
def save_feedback(payload: SaveIn):
    if not payload.boxes:
        raise HTTPException(status_code=400, detail="Draw at least one box before saving.")

    try:
        frame, is_clean = feedback_core.load_frame(payload.name, payload.t_ms)
    except ValueError:
        raise HTTPException(status_code=404, detail="Error: File not found")

    if frame is None:
        raise HTTPException(status_code=404, detail="Error: Could not read a frame for this file.")

    labelled = [
        (box.x_min, box.y_min, box.x_max, box.y_max, box.class_name)
        for box in payload.boxes
    ]

    try:
        saved = feedback_core.save_feedback_sample(
            frame, labelled, payload.name, payload.t_ms
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not save feedback: {exc}")

    return {
        "saved": [
            {
                "model": model_name,
                "label": feedback_core.FEEDBACK_MODELS[model_name]["label"],
                "image": image_path,
                "labels": label_path,
            }
            for model_name, image_path, label_path in saved
        ],
        "clean": is_clean,
    }


# References: this script has been written with the help of AI (chatgpt, Claude, Grok)