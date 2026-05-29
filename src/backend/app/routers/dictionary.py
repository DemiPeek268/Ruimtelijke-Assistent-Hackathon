from fastapi import APIRouter

from app.services import dictionary_service

router = APIRouter()


@router.get("/api/dictionary")
async def get_dictionary():
    dictionary = await dictionary_service.for_user()
    return dictionary.model_dump()
