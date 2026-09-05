from datetime import date
import re
import unicodedata

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.orm import Session, selectinload

from app.db.database import SessionLocal
from app.models.client_management import ClientPayment, ClientServiceStatus, ManagedClient, ProjectMilestone
from app.schemas.client_management import (
    ClientManagementDashboard,
    ManagedClientCreate,
    ManagedClientResponse,
    MilestoneCreate,
    MilestoneResponse,
    MilestoneUpdate,
    PaymentCreate,
    PaymentResponse,
    PaymentUpdate,
    ServiceDefinition,
    ServiceStatusResponse,
    ServiceStatusUpdate,
)


router = APIRouter(prefix="/client-management", tags=["Client management"])

SERVICES = [
    ServiceDefinition(key="frontend", label="Frontend"),
    ServiceDefinition(key="backend", label="Backend"),
    ServiceDefinition(key="postgresql", label="PostgreSQL"),
    ServiceDefinition(key="vercel", label="Vercel"),
    ServiceDefinition(key="render", label="Render"),
    ServiceDefinition(key="google_analytics", label="Google Analytics"),
    ServiceDefinition(key="facebook", label="Facebook"),
    ServiceDefinition(key="github", label="GitHub"),
    ServiceDefinition(key="email", label="Correo empresarial"),
    ServiceDefinition(key="hostinger", label="Hostinger"),
    ServiceDefinition(key="dbeaver", label="DBeaver"),
]


def get_client_or_404(db: Session, client_id: int) -> ManagedClient:
    client = db.query(ManagedClient).filter(ManagedClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente administrado no encontrado.")
    return client


def make_unique_slug(db: Session, name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "cliente"
    base = base[:90].rstrip("-")
    slug = base
    suffix = 2
    while db.query(ManagedClient.id).filter(ManagedClient.slug == slug).first():
        slug = f"{base[:90 - len(str(suffix))]}-{suffix}"
        suffix += 1
    return slug


def refresh_payment_statuses(db: Session) -> None:
    today = date.today()
    open_items = db.query(ClientPayment).filter(ClientPayment.status != "paid").all()
    changed = False
    for item in open_items:
        expected = "overdue" if item.due_date and item.due_date < today else "pending"
        if item.status != expected:
            item.status = expected
            changed = True
    if changed:
        db.commit()


def create_next_commitment(db: Session, source: ClientPayment, due_date: date | None) -> None:
    if not due_date:
        return
    duplicate = db.query(ClientPayment.id).filter(
        ClientPayment.client_id == source.client_id,
        ClientPayment.product_service == source.product_service,
        ClientPayment.due_date == due_date,
        ClientPayment.status != "paid",
    ).first()
    if duplicate:
        return
    db.add(ClientPayment(
        client_id=source.client_id,
        product_service=source.product_service,
        value=source.value,
        currency=source.currency,
        status="overdue" if due_date < date.today() else "pending",
        due_date=due_date,
        detail=source.detail,
    ))


@router.get("/dashboard", response_model=ClientManagementDashboard)
def dashboard():
    db: Session = SessionLocal()
    try:
        refresh_payment_statuses(db)
        clients = (
            db.query(ManagedClient)
            .options(
                selectinload(ManagedClient.service_statuses),
                selectinload(ManagedClient.milestones),
                selectinload(ManagedClient.payments),
            )
            .order_by(ManagedClient.name.asc())
            .all()
        )
        return ClientManagementDashboard(services=SERVICES, clients=clients)
    finally:
        db.close()


@router.post("/clients", response_model=ManagedClientResponse, status_code=status.HTTP_201_CREATED)
def create_client(payload: ManagedClientCreate):
    db: Session = SessionLocal()
    try:
        name = " ".join(payload.name.split())
        duplicate = db.query(ManagedClient.id).filter(ManagedClient.name.ilike(name)).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Ya existe un cliente con ese nombre.")

        website_url = payload.website_url.strip() if payload.website_url else None
        if website_url and not website_url.lower().startswith(("http://", "https://")):
            website_url = f"https://{website_url}"

        client = ManagedClient(
            name=name,
            slug=make_unique_slug(db, name),
            website_url=website_url,
            is_active=True,
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        return client
    finally:
        db.close()


@router.patch("/clients/{client_id}/services/{service_key}", response_model=ServiceStatusResponse)
def update_service(client_id: int, service_key: str, payload: ServiceStatusUpdate):
    if service_key not in {service.key for service in SERVICES}:
        raise HTTPException(status_code=400, detail="Servicio no válido.")
    db: Session = SessionLocal()
    try:
        get_client_or_404(db, client_id)
        item = (
            db.query(ClientServiceStatus)
            .filter(ClientServiceStatus.client_id == client_id, ClientServiceStatus.service_key == service_key)
            .first()
        )
        if not item:
            item = ClientServiceStatus(client_id=client_id, service_key=service_key)
            db.add(item)
        item.is_active = payload.is_active
        item.notes = payload.notes
        db.commit()
        db.refresh(item)
        return item
    finally:
        db.close()


@router.post("/clients/{client_id}/milestones", response_model=MilestoneResponse, status_code=status.HTTP_201_CREATED)
def create_milestone(client_id: int, payload: MilestoneCreate):
    db: Session = SessionLocal()
    try:
        get_client_or_404(db, client_id)
        item = ProjectMilestone(client_id=client_id, **payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        return item
    finally:
        db.close()


@router.patch("/milestones/{milestone_id}", response_model=MilestoneResponse)
def update_milestone(milestone_id: int, payload: MilestoneUpdate):
    db: Session = SessionLocal()
    try:
        item = db.query(ProjectMilestone).filter(ProjectMilestone.id == milestone_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Avance no encontrado.")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, field, value)
        db.commit()
        db.refresh(item)
        return item
    finally:
        db.close()


@router.delete("/milestones/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_milestone(milestone_id: int):
    db: Session = SessionLocal()
    try:
        item = db.query(ProjectMilestone).filter(ProjectMilestone.id == milestone_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Avance no encontrado.")
        db.delete(item)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    finally:
        db.close()


@router.post("/clients/{client_id}/payments", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
def create_payment(client_id: int, payload: PaymentCreate):
    db: Session = SessionLocal()
    try:
        get_client_or_404(db, client_id)
        data = payload.model_dump()
        if data["status"] == "paid" and not data["payment_date"]:
            data["payment_date"] = date.today()
        item = ClientPayment(client_id=client_id, **data)
        db.add(item)
        db.flush()
        if item.status == "paid":
            create_next_commitment(db, item, item.next_payment_date)
        db.commit()
        db.refresh(item)
        return item
    finally:
        db.close()


@router.patch("/payments/{payment_id}", response_model=PaymentResponse)
def update_payment(payment_id: int, payload: PaymentUpdate):
    db: Session = SessionLocal()
    try:
        item = db.query(ClientPayment).filter(ClientPayment.id == payment_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Pago no encontrado.")
        data = payload.model_dump(exclude_unset=True)
        was_paid = item.status == "paid"
        if data.get("status") == "paid" and "payment_date" not in data and not item.payment_date:
            data["payment_date"] = date.today()
        for field, value in data.items():
            setattr(item, field, value)
        if item.status == "paid" and (not was_paid or "next_payment_date" in data):
            create_next_commitment(db, item, item.next_payment_date)
        db.commit()
        db.refresh(item)
        return item
    finally:
        db.close()
