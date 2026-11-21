import {feedback, field} from '../components/common/fields.js';
import {empty, panel, pill} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {RECEIPT, REVIEW} from '../constants/enums.js';
import {handler} from '../hooks/action.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {button, el, link, p} from '../utils/dom.js';
import {date} from '../utils/format.js';
import {runPage} from './run.js';

function issueForm(dates, message) {
  const submit = button('开具调账单', {class:'primary', type:'submit', 'data-testid':'issue-bill'});
  return el('form', {class:'fields', onSubmit:handler(submit, message, async event => {
    const data = new FormData(event.target);
    const result = await workspace.issueBill({posting_date:data.get('posting_date')});
    if (result.bill) { location.hash = `#delivery/${result.bill.id}`; return; }
    message.textContent = result.message;
  })}, field({key:'posting_date', label:'结算日', type:'select', options:dates}, dates[0]), submit);
}

function billPanel(bill, refresh) {
  const message = feedback();
  const download = button('下载调账单 CSV', {class:'quiet'});
  download.addEventListener('click', handler(download, message, () =>
    workspace.download(`/adjustments/bills/${bill.id}/export`, `调账单-${bill.bill_no}.csv`)));
  const pending = bill.lines.filter(line => line.state === 'pending');
  const confirmAll = session.canReview && pending.length > 1
    && button(`确认全部待回执（${pending.length} 行）`, {class:'primary'});
  if (confirmAll) confirmAll.addEventListener('click', handler(confirmAll, message, async () => {
    await workspace.receipt({line_ids:pending.map(line => line.id)});
    await refresh();
  }));
  const lines = table([
    {key:'zone', label:'校区'}, {key:'merchant_group', label:'档口组'},
    {key:'expected_cents', label:'应结额（分）'},
    {key:'confirmed_before_cents', label:'开单前已确认（分）'},
    {key:'delta_cents', label:'调账额（分）'},
    {label:'回执', render:row=>pill(RECEIPT[row.state], row.state)},
    {label:'确认', render:row=>row.confirmed_by ? `${row.confirmed_by} · ${date(row.confirmed_at)}` : '—'},
    session.canReview && {label:'操作', render:row=>{
      if (row.state !== 'pending') return '—';
      const action = button('确认回执', {class:'quiet'});
      action.addEventListener('click', handler(action, message, async () => {
        await workspace.receipt({line_ids:[row.id]});
        await refresh();
      }));
      return action;
    }},
  ].filter(Boolean), bill.lines, {caption:`调账单 ${bill.bill_no} 调账行`});
  const held = bill.held_groups.length > 0 && el('div', {class:'decision'},
    p('开单时暂缓（等回执），回执后按最新复核结果重算'),
    el('ul', {class:'method-list'}, bill.held_groups.map(group =>
      el('li', {}, `${group.zone} · ${group.merchant_group}`))));
  return panel(`调账单 ${bill.bill_no}`,
    el('div', {class:'actions'}, pill(RECEIPT[bill.state], bill.state), download, confirmAll),
    p(`结算日 ${bill.posting_date} · 基于运行 ${bill.run_id} · ${bill.author} 于 ${date(bill.created_at)} 开单`, 'subtle'),
    lines, held, message);
}

export async function deliveryPage(route, refresh) {
  const {spec, runs} = workspace;
  const message = feedback();
  const issueMessage = feedback();
  const artifacts = table([
    {label:'报告', render:row=>link(row.name,`#results/${row.id}`)},
    {label:'复核', render:row=>pill(REVIEW[row.review],row.review)},
    {label:'计算时间', render:row=>date(row.finished_at)},
    {label:'下载', render:row=>{
      const download = button('下载 CSV',{class:'quiet'});
      download.addEventListener('click', handler(download,message,() =>
        workspace.download(`/runs/${row.id}/export`,`${spec.short_name}-${row.id}.csv`)));
      return download;
    }},
  ], runs.filter(row=>row.status==='complete'), {caption:'可导出的结果', empty:'完成计算后会生成对应的报告。'});
  const dates = [...new Set(runs.filter(row => row.status==='complete' && row.review==='accepted')
    .map(row => row.posting_date).filter(Boolean))].sort().reverse();
  const bills = await workspace.bills();
  const adjustment = panel('调账单',
    p('按结算日对最新复核应结额与财务已确认累计轧差开单，缺组按零计、负差照常开单；同组有等回执的调账行时该组暂缓，其他组照发。已开账单内容锁定，重复下载不变。',
      'subtle'),
    session.canWrite
      ? (dates.length ? issueForm(dates, issueMessage) : p('还没有通过复核的清分结果，请先在结算复核中通过。','subtle'))
      : p('只读角色可查看和下载调账单。','subtle'),
    table([
      {label:'单号', render:row=>link(row.bill_no,`#delivery/${row.id}`)},
      {key:'posting_date', label:'结算日'},
      {key:'line_count', label:'行数'},
      {key:'pending_count', label:'待回执'},
      {key:'delta_cents', label:'调账合计（分）'},
      {label:'状态', render:row=>pill(RECEIPT[row.state],row.state)},
      {key:'author', label:'开单人'},
      {label:'开单时间', render:row=>date(row.created_at)},
    ], bills, {caption:'调账单', empty:'还没有调账单，通过复核后可在此开单。'}),
    issueMessage);
  const selected = route.id ? await workspace.bill(route.id).catch(() => undefined) : null;
  const detail = selected ? billPanel(selected, refresh)
    : route.id ? panel('调账单', empty('找不到该调账单。','#delivery','返回调账单列表')) : null;
  const delivery = spec.scheduled ? panel('站内分发回执', table([
    {key:'recipient',label:'收件团队'},
    {label:'回执',render:row=>pill(row.state==='delivered'?'已投递':'已拦截',row.state)},
    {key:'detail',label:'说明'}, {label:'时间',render:row=>date(row.created_at)},
    {label:'查看',render:row=>link(`运行 ${row.run_id}`,`#results/${row.run_id}`)},
  ],await workspace.deliveries(),{caption:'站内收件箱',empty:'计划到时执行，回执将在此更新。'})) : null;
  return el('div',{}, panel(spec.pages[5], p('按运行批次下载 CSV，复核状态随报告保留。','subtle'), artifacts, message),
    adjustment, detail, delivery, spec.scheduled && await runPage({...route,scheduling:true},refresh));
}
