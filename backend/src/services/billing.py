"""调账单开单与回执确认：按结算日串行开单，回执按行幂等确认。"""

from uuid import uuid4
from sqlalchemy import select, text
from src.constants.enums import Receipt, Review, Status
from src.domain.billing import payable_groups, plan_lines, valid_day
from src.models.billing import AdjustmentBill, AdjustmentLine
from src.models.jobs import Run
from src.services.audit import record
from src.utils.time import now


def _latest_reviewed_run(db, day):
    query = (select(Run)
             .where(Run.status == Status.COMPLETE, Run.review == Review.ACCEPTED,
                    Run.params['posting_date'].as_string() == day)
             .order_by(Run.id.desc()).limit(1))
    return db.scalar(query)


def issue(db, posting_date, actor):
    """为结算日开具调账单。返回 (bill, held, settled)，无可开行时 bill 为 None。

    咨询锁按结算日串行化开单；等回执唯一索引兜底，并发与重试都不会多发或漏发。
    """
    day = valid_day(posting_date)
    if db.get_bind().dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': f'adjustment-issue:{day}'})
    run = _latest_reviewed_run(db, day)
    if run is None:
        raise ValueError('该结算日还没有通过复核的清分结果，请先在结算复核中通过')
    existing = db.scalars(select(AdjustmentLine).where(AdjustmentLine.posting_date == day)).all()
    new_lines, held, settled = plan_lines(payable_groups(run.result), existing)
    if not new_lines:
        return None, held, settled
    bill = AdjustmentBill(bill_no=f'tmp-{uuid4().hex}', posting_date=day, run_id=run.id,
                          held_groups=held, author=actor.username)
    db.add(bill)
    db.flush()
    bill.bill_no = f'ADJ-{day.replace("-", "")}-{bill.id:04d}'
    for spec in new_lines:
        db.add(AdjustmentLine(bill_id=bill.id, posting_date=day, **spec))
    record(db, actor.username, 'adjustment.issued', bill.id, posting_date=day, run_id=run.id,
           lines=len(new_lines), held=len(held),
           delta_cents=sum(line['delta_cents'] for line in new_lines))
    return bill, held, settled


def confirm(db, line_ids, actor):
    """按行确认回执。已确认的行直接跳过，重试不会重复入账。返回 (lines, changed)。"""
    ids = sorted(set(line_ids))
    found = {line.id: line for line in db.scalars(
        select(AdjustmentLine).where(AdjustmentLine.id.in_(ids)).with_for_update())}
    missing = [str(line_id) for line_id in ids if line_id not in found]
    if missing:
        raise ValueError(f'找不到调账行 {", ".join(missing)}，请刷新后重试')
    stamp = now()
    changed = 0
    for line_id in ids:
        line = found[line_id]
        if line.state == Receipt.CONFIRMED:
            continue
        line.state = Receipt.CONFIRMED
        line.confirmed_by = actor.username
        line.confirmed_at = stamp
        changed += 1
        record(db, actor.username, 'adjustment.confirmed', line.id,
               bill_id=line.bill_id, delta_cents=line.delta_cents)
    return [found[line_id] for line_id in ids], changed
