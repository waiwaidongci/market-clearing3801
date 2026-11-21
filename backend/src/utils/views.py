from src.constants.enums import Receipt
from src.utils.time import iso


def dataset(item):
    return {'id': item.id, 'name': item.name, 'filename': item.filename, 'row_count': item.row_count,
            'checksum': item.checksum, 'author': item.author, 'created_at': iso(item.created_at)}


def run(item, detail=False):
    item_view = {'id': item.id, 'dataset_id': item.dataset_id, 'name': item.name, 'status': item.status,
                 'author': item.author, 'review': item.review, 'decision': item.decision,
                 'created_at': iso(item.created_at), 'finished_at': iso(item.finished_at),
                 'scheduled_at': iso(item.scheduled_at), 'schedule_id': item.schedule_id,
                 'posting_date': (item.params or {}).get('posting_date'),
                 'has_export': bool(item.export_file), 'error': item.error}
    if detail:
        item_view.update(params=item.params, result=item.result, review_note=item.review_note)
    return item_view


def schedule(item):
    from src.domain.spec import SPEC
    return {'id': item.id, 'name': item.name, 'dataset_id': item.dataset_id, 'recipient': item.recipient,
            'next_at': iso(item.next_at), 'repeat_daily': item.repeat_daily, 'enabled': item.enabled,
            'next_report_day': item.params.get(SPEC['schedule_date_param']) if item.enabled else None}


def delivery(item):
    return {'id': item.id, 'run_id': item.run_id, 'recipient': item.recipient,
            'state': item.state, 'detail': item.detail, 'created_at': iso(item.created_at)}


def adjustment_line(item):
    return {'id': item.id, 'bill_id': item.bill_id, 'posting_date': item.posting_date,
            'zone': item.zone, 'merchant_group': item.merchant_group,
            'expected_cents': item.expected_cents, 'confirmed_before_cents': item.confirmed_before_cents,
            'delta_cents': item.delta_cents, 'state': item.state,
            'confirmed_by': item.confirmed_by, 'confirmed_at': iso(item.confirmed_at)}


def adjustment_bill(item, lines):
    pending = sum(1 for line in lines if line.state == Receipt.PENDING)
    return {'id': item.id, 'bill_no': item.bill_no, 'posting_date': item.posting_date,
            'run_id': item.run_id, 'author': item.author, 'created_at': iso(item.created_at),
            'held_groups': item.held_groups, 'line_count': len(lines), 'pending_count': pending,
            'confirmed_count': len(lines) - pending,
            'delta_cents': sum(line.delta_cents for line in lines),
            'state': Receipt.PENDING if pending else Receipt.CONFIRMED}
