from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/healthcheck")
async def healthcheck():
    return {"status": "ok"}


@router.get("/readiness")
async def readiness(request: Request):
    ready = getattr(request.app.state, "ready", False)
    if not ready:
        return {"status": "warming_up"}
    return {"status": "ready"}
