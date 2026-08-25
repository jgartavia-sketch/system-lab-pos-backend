from datetime import date

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.orm import Session, selectinload

from app.db.database import SessionLocal
from app.models.client_management import ClientPayment, ClientServiceStatus, ManagedClient, ProjectMilestone
from app.schemas.client_management import (
    ClientManagementDashboard,
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


@router.get("/dashboard", response_model=ClientManagementDashboard)
def dashboard():
    db: Session = SessionLocal()
    try:
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
        if data.get("status") == "paid" and "payment_date" not in data and not item.payment_date:
            data["payment_date"] = date.today()
        for field, value in data.items():
            setattr(item, field, value)
        db.commit()
        db.refresh(item)
        return item
    finally:
        db.close()
