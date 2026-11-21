from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from src.config.database import connection
from src.constants.enums import Role
from src.controllers.auth import allow, current
from src.models.billing import AdjustmentBill, AdjustmentLine
from src.models.identity import User
from src.schemas.requests import IssueRequest, ReceiptRequest
from src.services import billing
from src.utils import views
from src.utils.exports import bill_csv

router = APIRouter(prefix='/adjustments')


def require_bill(db, bill_id):
    item = db.get(AdjustmentBill, bill_id)
    if not item:
        raise HTTPException(404, '找不到该调账单')
    return item


@router.get('/bills')
def bills(db: Session = Depends(connection), actor: User = Depends(current)):
    items = db.scalars(select(AdjustmentBill).order_by(AdjustmentBill.id.desc()).limit(100)).all()
    lines = db.scalars(select(AdjustmentLine).where(AdjustmentLine.bill_id.in_([item.id for item in items]))
                       .order_by(AdjustmentLine.id)).all() if items else []
    grouped = {item.id: [] for item in items}
    for line in lines:
        grouped[line.bill_id].append(line)
    return [views.adjustment_bill(item, grouped[item.id]) for item in items]


@router.get('/bills/{bill_id}')
def detail(bill_id: int, db: Session = Depends(connection), actor: User = Depends(current)):
    item = require_bill(db, bill_id)
    return {**views.adjustment_bill(item, item.lines),
            'lines': [views.adjustment_line(line) for line in item.lines]}


@router.get('/bills/{bill_id}/export')
def export(bill_id: int, db: Session = Depends(connection), actor: User = Depends(current)):
    item = require_bill(db, bill_id)
    filename = quote(f'调账单-{item.bill_no}.csv')
    return Response(bill_csv(item, item.lines), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{filename}"})


@router.post('/issue')
def issue(body: IssueRequest, response: Response, db: Session = Depends(connection),
          actor: User = Depends(allow(Role.ADMIN, Role.ANALYST))):
    try:
        bill, held, settled = billing.issue(db, body.posting_date, actor)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '该结算日存在等回执的调账行，相关组已暂缓，请回执后重试') from None
    result = {'bill': None, 'held': held, 'settled': settled}
    if bill is None:
        result['message'] = ('相关组都在等回执，本次全部暂缓' if held
                             else '应结额与财务已确认累计一致，无需开单')
        return result
    response.status_code = 201
    result['bill'] = {**views.adjustment_bill(bill, bill.lines),
                      'lines': [views.adjustment_line(line) for line in bill.lines]}
    result['message'] = f'已开具调账单 {bill.bill_no}，共 {len(bill.lines)} 行'
    if held:
        result['message'] += f'，{len(held)} 组等回执暂缓'
    return result


@router.post('/receipts')
def receipts(body: ReceiptRequest, db: Session = Depends(connection),
             actor: User = Depends(allow(Role.ADMIN))):
    lines, changed = billing.confirm(db, body.line_ids, actor)
    db.commit()
    return {'lines': [views.adjustment_line(line) for line in lines], 'confirmed': changed,
            'message': f'已确认 {changed} 行回执' if changed else '所选行此前已确认，未重复入账'}
