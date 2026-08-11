import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.database import init_db, async_session
from app.seed import seed_database
from app.crawlers.scheduler import start_scheduler, stop_scheduler, get_scheduler
from app.services.notify_scheduler import register_notify_job, register_benefit_inspection_job
from app.api import cards, activities, crawlers, user, accounts, recommend, reminders, custom, export, bills, bank_offers, admin, spending, bill_ocr

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"启动 {settings.APP_NAME} v{settings.APP_VERSION}")
    await init_db()
    async with async_session() as db:
        await seed_database(db)
    start_scheduler()
    # Register daily notification job
    scheduler = get_scheduler()
    register_notify_job(scheduler)
    register_benefit_inspection_job(scheduler)
    yield
    stop_scheduler()
    logger.info("应用关闭")


app = FastAPI(
    title="ccreward-cn 国内信用卡权益与商家活动聚合",
    version=settings.APP_VERSION,
    description="聚合国内信用卡权益与多平台商家活动，支持搜索与比价",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cards.router, prefix="/api")
app.include_router(activities.router, prefix="/api")
app.include_router(crawlers.router, prefix="/api")
app.include_router(user.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")
app.include_router(recommend.router, prefix="/api")
app.include_router(reminders.router, prefix="/api")
app.include_router(custom.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(bills.router, prefix="/api")
app.include_router(bank_offers.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(spending.router, prefix="/api")
app.include_router(bill_ocr.router, prefix="/api")

WEB_DIR = Path(__file__).resolve().parent / "web"
if WEB_DIR.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


@app.get("/", include_in_schema=False)
async def root():
    index = WEB_DIR / "index.html"
    if index.exists():
        return FileResponse(index, headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})
    return {"message": "ccreward-cn API", "docs": "/docs"}


@app.get("/manifest.json", include_in_schema=False)
async def manifest():
    mf = WEB_DIR / "manifest.json"
    if mf.exists():
        return FileResponse(mf, media_type="application/manifest+json")
    return {"error": "not found"}


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    sw = WEB_DIR / "sw.js"
    if sw.exists():
        return FileResponse(sw, media_type="application/javascript", headers={"Cache-Control": "no-cache"})
    return {"error": "not found"}


@app.get("/api/health", tags=["系统"])
async def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}
