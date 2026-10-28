import pytest
from sqlalchemy import select
from test_pos import env, good, setup_sale, order, req
from app.pos.admin_delete import router
from app.pos.models import Business, Account, Membership, Product, ConnectLink


def call(env, ident, who=1):
    if not getattr(env[0].app.state, 'delete_registered', False):
        env[0].app.include_router(router)
        env[0].app.state.delete_registered = True
    return env[0].delete(f'/pos-api/admin/businesses/{ident}', headers=env[1](who))


def test_empty_local_deletes_only_local_and_membership(env):
    assert call(env, 1).status_code == 200
    with env[2]() as db:
        assert db.get(Business, 1) is None
        assert db.get(Account, 1) is not None
        assert db.get(Business, 2) is not None
        assert not list(db.scalars(select(Membership).where(Membership.business_id == 1)))
    assert call(env, 1).status_code == 404


def test_only_ceo_can_delete_and_auth_is_required(env):
    assert call(env, 1, who=2).status_code == 403
    assert env[0].delete('/pos-api/admin/businesses/1').status_code == 401
    with env[2]() as db:
        assert db.get(Business, 1)


def test_connected_local_is_protected_even_without_history(env):
    with env[2].begin() as db:
        db.add(ConnectLink(business_id=1, provider='zenit'))
    assert call(env, 1).status_code == 409
    with env[2]() as db:
        assert db.get(ConnectLink, 1)
        assert db.get(Business, 1)


def test_catalog_is_protected_and_other_empty_duplicate_can_be_deleted(env):
    with env[2].begin() as db:
        db.add(Product(business_id=1, name='Servicio', sku='S', price=100))
    assert call(env, 1).status_code == 409
    assert call(env, 2).status_code == 200
    with env[2]() as db:
        assert db.get(Business, 1)
        assert db.scalar(select(Product).where(Product.business_id == 1))
        assert db.get(Account, 2)


def test_sale_and_credit_history_are_preserved(env):
    from test_pos_zenit_credit import credit
    sale, receivable, _ = credit(env)
    assert call(env, 1).status_code == 409
    assert good(req(env, '/receivables'))['accounts'][0]['id'] == receivable['id']
