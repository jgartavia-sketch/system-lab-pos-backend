from datetime import date
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.models.business_finance import BusinessFinanceMovement
from app.models.client_management import ManagedClient
from app.schemas.business_finance import FinanceMovementCreate, FinanceMovementResponse, FinanceSummary

router = APIRouter(prefix="/client-management/finances", tags=["System Lab finances"])

def month_bounds(month: str):
    try:
        year, mon = map(int, month.split("-"))
        start = date(year, mon, 1)
        end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
        return start, end
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Mes inválido. Usá YYYY-MM.") from exc

@router.get("/movements", response_model=list[FinanceMovementResponse])
def list_movements(month: str = Query(..., pattern=r"^\d{4}-\d{2}$")):
    start, end = month_bounds(month); db = SessionLocal()
    try:
        return db.query(BusinessFinanceMovement).filter(BusinessFinanceMovement.movement_date >= start, BusinessFinanceMovement.movement_date < end).order_by(BusinessFinanceMovement.movement_date.desc(), BusinessFinanceMovement.id.desc()).all()
    finally: db.close()

@router.post("/movements", response_model=FinanceMovementResponse, status_code=status.HTTP_201_CREATED)
def create_movement(payload: FinanceMovementCreate):
    db = SessionLocal()
    try:
        if payload.client_id and not db.query(ManagedClient.id).filter(ManagedClient.id == payload.client_id).first():
            raise HTTPException(status_code=404, detail="Cliente administrado no encontrado.")
        item = BusinessFinanceMovement(**payload.model_dump())
        db.add(item); db.commit(); db.refresh(item); return item
    finally: db.close()

@router.delete("/movements/{movement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_movement(movement_id: int):
    db = SessionLocal()
    try:
        item = db.query(BusinessFinanceMovement).filter(BusinessFinanceMovement.id == movement_id).first()
        if not item: raise HTTPException(status_code=404, detail="Movimiento no encontrado.")
        db.delete(item); db.commit(); return Response(status_code=status.HTTP_204_NO_CONTENT)
    finally: db.close()

@router.get("/summary", response_model=FinanceSummary)
def finance_summary(month: str = Query(..., pattern=r"^\d{4}-\d{2}$"), currency: str = Query("CRC", pattern="^(CRC|USD)$")):
    start, end = month_bounds(month); db = SessionLocal()
    try:
        rows = db.query(BusinessFinanceMovement.movement_type, func.coalesce(func.sum(BusinessFinanceMovement.amount), 0), func.count(BusinessFinanceMovement.id)).filter(BusinessFinanceMovement.movement_date >= start, BusinessFinanceMovement.movement_date < end, BusinessFinanceMovement.currency == currency).group_by(BusinessFinanceMovement.movement_type).all()
        income=Decimal("0"); expenses=Decimal("0"); count=0
        for kind,total,qty in rows:
            count += qty
            if kind=="income": income=Decimal(total)
            elif kind=="expense": expenses=Decimal(total)
        return FinanceSummary(income=income, expenses=expenses, profit=income-expenses, movement_count=count)
    finally: db.close()
