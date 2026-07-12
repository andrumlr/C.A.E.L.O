from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.chat import router as chat_router
from api.conversations import router as conversations_router
from api.core_values import router as core_values_router
from api.documents import router as documents_router
from core.auth import require_api_key
from core.rate_limit import RateLimitMiddleware
from db.database import init_db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.railway\.app|http://localhost:\d+",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

init_db()

app.include_router(chat_router, prefix="/chat", dependencies=[Depends(require_api_key)])
app.include_router(documents_router, prefix="/documents", dependencies=[Depends(require_api_key)])
app.include_router(conversations_router, prefix="/conversations", dependencies=[Depends(require_api_key)])
app.include_router(core_values_router, prefix="/core-values", dependencies=[Depends(require_api_key)])