from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.documents import router as documents_router
from app.api.v1.invitations import router as invitations_router
from app.api.v1.interviews import router as interviews_router
from app.api.v1.interview_invitations import router as interview_invitations_router
from app.api.v1.knowledge_bases import router as knowledge_bases_router
from app.api.v1.retrieval import router as retrieval_router
from app.api.v1.recruitment import router as recruitment_router
from app.api.v1.users import router as users_router
from app.api.v1.workspaces import router as workspaces_router


router = APIRouter()
router.include_router(auth_router)
router.include_router(documents_router)
router.include_router(invitations_router)
router.include_router(interviews_router)
router.include_router(interview_invitations_router)
router.include_router(knowledge_bases_router)
router.include_router(retrieval_router)
router.include_router(recruitment_router)
router.include_router(users_router)
router.include_router(workspaces_router)
