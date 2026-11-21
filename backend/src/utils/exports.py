import csv
import io
from src.config.settings import ARTIFACTS
from src.constants.enums import Receipt
from src.utils.time import iso


def safe_cell(value):
    if isinstance(value, str) and (value.lstrip().startswith(('=', '+', '-', '@'))
                                   or value.startswith(('\t', '\r', '\n'))):
        return "'" + value
    return value


def write_report(run_id, attempt, result):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    name = f'analysis-{run_id}-{attempt}.csv'
    path = ARTIFACTS / name
    staging = path.with_suffix('.tmp')
    with staging.open('w', encoding='utf-8-sig', newline='') as output:
        writer = csv.writer(output)
        writer.writerow([safe_cell(result['headline'])])
        writer.writerow([safe_cell(result.get('note', ''))])
        for metric in result['metrics']:
            writer.writerow([safe_cell(metric['label']), safe_cell(metric['value']), safe_cell(metric.get('detail', ''))])
        for table in result['tables']:
            writer.writerow([])
            writer.writerow([safe_cell(table['title'])])
            columns = table['columns']
            writer.writerow([safe_cell(column['label']) for column in columns])
            writer.writerows([safe_cell(row.get(column['key'])) for column in columns] for row in table['rows'])
    staging.replace(path)
    return name


def bill_csv(bill, lines):
    """Render an issued adjustment bill from its stored lines, so re-downloads never change."""
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer)
    writer.writerow(['调账单', bill.bill_no])
    writer.writerow(['结算日', bill.posting_date])
    writer.writerow(['基于运行', bill.run_id])
    writer.writerow(['开单人', safe_cell(bill.author)])
    writer.writerow(['开单时间', iso(bill.created_at)])
    writer.writerow([])
    writer.writerow(['行号', '校区', '档口组', '应结额（分）', '开单前已确认（分）', '调账额（分）',
                     '回执状态', '确认人', '确认时间'])
    for index, line in enumerate(lines, 1):
        writer.writerow([index, safe_cell(line.zone), safe_cell(line.merchant_group),
                         line.expected_cents, line.confirmed_before_cents, line.delta_cents,
                         '已确认' if line.state == Receipt.CONFIRMED else '等回执',
                         safe_cell(line.confirmed_by or ''), iso(line.confirmed_at) or ''])
    if bill.held_groups:
        writer.writerow([])
        writer.writerow(['开单时暂缓（等回执）'])
        writer.writerow(['校区', '档口组'])
        writer.writerows([safe_cell(group['zone']), safe_cell(group['merchant_group'])]
                         for group in bill.held_groups)
    return '\ufeff' + buffer.getvalue()

