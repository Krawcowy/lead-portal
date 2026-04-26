from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import Base, engine, SessionLocal
from app.models import Source, Lead
from app.extractor import extract_leads_from_source

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from app.models import Source, Lead, ScanSettings

Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    sources_count = db.query(Source).count()
    leads_count = db.query(Lead).count()
    new_leads_count = db.query(Lead).filter(Lead.status == "new").count()

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "sources_count": sources_count,
            "leads_count": leads_count,
            "new_leads_count": new_leads_count
        }
    )


@app.get("/sources")
def sources_page(request: Request, db: Session = Depends(get_db)):
    sources = db.query(Source).order_by(Source.created_at.desc()).all()

    return templates.TemplateResponse(
        request,
        "sources.html",
        {"sources": sources}
    )


@app.post("/sources")
def add_source(
    name: str = Form(...),
    url: str = Form(...),
    db: Session = Depends(get_db)
):
    source = Source(name=name, url=url)
    db.add(source)
    db.commit()

    return RedirectResponse("/sources", status_code=303)

@app.post("/sources/{source_id}/update")
def update_source(
    source_id: int,
    name: str = Form(...),
    url: str = Form(...),
    active: str = Form(None),
    db: Session = Depends(get_db)
):
    source = db.query(Source).filter(Source.id == source_id).first()

    if source:
        source.name = name
        source.url = url
        source.active = True if active == "on" else False
        db.commit()

    return RedirectResponse("/sources", status_code=303)


@app.post("/sources/{source_id}/delete")
def delete_source(
    source_id: int,
    db: Session = Depends(get_db)
):
    source = db.query(Source).filter(Source.id == source_id).first()

    if source:
        db.delete(source)
        db.commit()

    return RedirectResponse("/sources", status_code=303)

@app.get("/leads")
def leads_page(
    request: Request,
    asset_type: str = None,
    category: str = None,
    source_id: int = None,
    sort: str = "newest",
    db: Session = Depends(get_db)
):
    query = db.query(Lead)

    if asset_type:
        query = query.filter(Lead.asset_type == asset_type)

    if category:
        query = query.filter(Lead.category == category)

    if source_id:
        query = query.filter(Lead.source_id == source_id)

    if sort == "oldest":
        query = query.order_by(Lead.created_at.asc())
    elif sort == "price_low":
        query = query.order_by(Lead.price.asc())
    elif sort == "price_high":
        query = query.order_by(Lead.price.desc())
    else:
        query = query.order_by(Lead.created_at.desc())

    leads = query.all()

    sources = db.query(Source).all()

    source_counts = {}
    for s in sources:
        source_counts[s.id] = db.query(Lead).filter(Lead.source_id == s.id).count()

    asset_counts = {
        "nieruchomości": db.query(Lead).filter(Lead.asset_type == "nieruchomości").count(),
        "ruchomości": db.query(Lead).filter(Lead.asset_type == "ruchomości").count(),
        "inne": db.query(Lead).filter(Lead.asset_type == "inne").count(),
    }

    category_names = [
        "mieszkania",
        "domy",
        "lokale użytkowe",
        "działki / grunty",
        "garaże / miejsca postojowe",
        "samochody / pojazdy",
        "maszyny / sprzęt",
        "wyposażenie / meble",
        "towary / zapasy",
        "udziały / prawa",
    ]

    category_counts = {}
    for cat in category_names:
        category_counts[cat] = db.query(Lead).filter(Lead.category == cat).count()

    return templates.TemplateResponse(
        request,
        "leads.html",
        {
            "leads": leads,
            "sources": sources,
            "source_counts": source_counts,
            "asset_counts": asset_counts,
            "category_counts": category_counts,
            "selected_asset_type": asset_type,
            "selected_category": category,
            "selected_source_id": source_id,
            "selected_sort": sort
        }
    )

def run_scan():
    db = SessionLocal()
    added = 0

    try:
        sources = db.query(Source).filter(Source.active == True).all()

        for source in sources:
            try:
                found_leads = extract_leads_from_source(source.url)

                for item in found_leads:
                    exists = db.query(Lead).filter(Lead.url == item["url"]).first()

                    if not exists:
                        lead = Lead(
                            title=item["title"],
                            url=item["url"],
                            source_id=source.id,
                            notes=item.get("description"),
                            price=item.get("price"),
                            deadline=item.get("deadline"),
                            asset_type=item.get("asset_type"),
                            category=item.get("category") or "inne"
                        )
                        db.add(lead)
                        added += 1

            except Exception as e:
                print(f"Błąd przy źródle {source.url}: {e}")

        settings = db.query(ScanSettings).first()
        if settings:
            settings.last_run_at = datetime.utcnow()

        db.commit()

    finally:
        db.close()

    print(f"Skanowanie zakończone. Dodano: {added}")
    return added

@app.post("/scan")
def scan_sources():
    run_scan()
    return RedirectResponse("/", status_code=303)
  
def scheduled_scan_job():
    db = SessionLocal()

    try:
        settings = db.query(ScanSettings).first()

        if settings and settings.enabled:
            run_scan()

    finally:
        db.close()


@app.on_event("startup")
def start_scheduler():
    db = SessionLocal()

    try:
        settings = db.query(ScanSettings).first()

        if not settings:
            settings = ScanSettings(enabled=False, interval_hours=24)
            db.add(settings)
            db.commit()

        scheduler.add_job(
            scheduled_scan_job,
            "interval",
            hours=settings.interval_hours,
            id="auto_scan",
            replace_existing=True
        )

        scheduler.start()

    finally:
        db.close()


@app.on_event("shutdown")
def shutdown_scheduler():
    scheduler.shutdown()


    @app.get("/scan-settings")
def scan_settings_page(request: Request, db: Session = Depends(get_db)):
    settings = db.query(ScanSettings).first()

    if not settings:
        settings = ScanSettings(enabled=False, interval_hours=24)
        db.add(settings)
        db.commit()

    return templates.TemplateResponse(
        request,
        "scan_settings.html",
        {"settings": settings}
    )


@app.post("/scan-settings")
def update_scan_settings(
    enabled: str = Form(None),
    interval_hours: int = Form(...),
    db: Session = Depends(get_db)
):
    settings = db.query(ScanSettings).first()

    if not settings:
        settings = ScanSettings()
        db.add(settings)

    settings.enabled = True if enabled == "on" else False
    settings.interval_hours = interval_hours

    db.commit()

    scheduler.reschedule_job(
        "auto_scan",
        trigger="interval",
        hours=interval_hours
    )

    return RedirectResponse("/scan-settings", status_code=303)