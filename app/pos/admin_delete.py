from fastapi import APIRouter, Depends
from sqlalchemy import select
from app.db.database import get_db
from app.pos.models import Account, Membership, Register, Order, Movement, Audit, FinancialEntry
from app.pos.security import ceo
from app.pos.routes import fail, commit

router = APIRouter(prefix="/pos-api/admin", tags=["POS admin"])

@router.delete("/accounts/{ident}")
def delete_account(ident: int, actor=Depends(ceo), db=Depends(get_db)):
    target = db.get(Account, ident)
    if not target:
        fail("Cuenta no encontrada.", 404)
    if target.ceo:
        fail("La cuenta CEO no se puede eliminar.", 403)
    if target.id == actor.id:
        fail("No podÃ©s eliminar tu propia cuenta.", 403)

    # No borramos historia contable/operativa. Si la cuenta ya participÃ³ en
    # operaciones, debe conservarse para auditorÃ­a y puede suspenderse desde el panel.
    historical = any((
        db.scalar(select(Register.id).where(
            (Register.opened_by == target.id) | (Register.closed_by == target.id)
        ).limit(1)),
        db.scalar(select(Order.id).where(Order.account_id == target.id).limit(1)),
        db.scalar(select(Movement.id).where(Movement.account_id == target.id).limit(1)),
        db.scalar(select(Audit.id).where(
            (Audit.actor_id == target.id) | (Audit.approver_id == target.id)
        ).limit(1)),
        db.scalar(select(FinancialEntry.id).where(FinancialEntry.account_id == target.id).limit(1)),
    ))
    if historical:
        fail("Esta cuenta ya tiene historial operativo y no se puede borrar sin romper la auditorÃ­a. Suspendela desde Administrar acceso.", 409)

    for membership in db.scalars(select(Membership).where(Membership.account_id == target.id)).all():
        db.delete(membership)
    db.delete(target)
    commit(db)
    return {"ok": True, "deleted_id": ident}