from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.models.client_management import ManagedClient
from app.models.client_event import ClientEvent
from app.schemas.client_event import ClientEventCreate, ClientEventResponse

router = APIRouter(prefix="/client-management", tags=["Client management events"])

@router.get("/events", response_model=list[ClientEventResponse])
def list_events():
    db: Session = SessionLocal()
    try: return db.query(ClientEvent).order_by(ClientEvent.event_date.asc(), ClientEvent.id.asc()).all()
    finally: db.close()

@router.post("/clients/{client_id}/events", response_model=ClientEventResponse, status_code=status.HTTP_201_CREATED)
def create_event(client_id:int, payload:ClientEventCreate):
    db: Session = SessionLocal()
    try:
        if not db.query(ManagedClient.id).filter(ManagedClient.id==client_id).first(): raise HTTPException(status_code=404,detail="Cliente administrado no encontrado.")
        item=ClientEvent(client_id=client_id, **payload.model_dump()); db.add(item); db.commit(); db.refresh(item); return item
    finally: db.close()

@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id:int):
    db: Session = SessionLocal()
    try:
        item=db.query(ClientEvent).filter(ClientEvent.id==event_id).first()
        if not item: raise HTTPException(status_code=404,detail="Evento no encontrado.")
        db.delete(item); db.commit(); return Response(status_code=status.HTTP_204_NO_CONTENT)
    finally: db.close()
