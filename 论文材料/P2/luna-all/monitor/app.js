'use strict';
const $ = (id) => document.getElementById(id);
const stateNames = {NOT_CONNECTED:'未连接实验',READY:'准备完成',RUNNING:'运行中',PAUSED:'已暂停',BLOCKED:'受限 / 等待授权',COMPLETED:'已完成',COMPLETED_WITH_GAPS:'已结束 · 有缺口',STOPPED:'已停止'};
const unitNames = {technical_complete:'技术验证已结算（非原生判分）',not_started:'未启动',running:'进行中',awaiting_judge:'Actor已结束 · 待判分',complete:'已判分',technical_error:'技术异常',response_unknown:'响应未知',blocked:'未调度 · 阻塞'};
const roleNames = {actor:'Actor',semantic:'语义 / 意图',content:'Content审查',derived:'Derived审查',judge:'Judge判分',idle:'空闲'};
const phaseNames = {BINDING:'配置绑定',TECH:'技术验证',CORE:'正式实验',JUDGING:'判分',REPORT:'报告',IDLE:'尚未启动'};
const matchNames = {UNVERIFIED:'尚未核对',MATCHED_OBSERVED_CONTRACT:'已核对观测合同',TRANSPORT_MISMATCH:'传输 / 上下文不同',JUDGE_MISMATCH:'Judge不同',LIBRARY_MISMATCH:'组件不同',MULTIPLE_MISMATCHES:'存在多项差异',HISTORY_ONLY:'仅历史参考'};
let latest=null;
let fetchError=false;
let busy=false;
function text(id,value){$(id).textContent=value;}
function stamp(t){if(!t)return '—';const d=new Date(t);return Number.isNaN(d.getTime())?'—':d.toLocaleTimeString([], {hour12:false});}
function age(t){return t ? Math.max(0,(Date.now()-Date.parse(t))/1000) : null;}
function duration(seconds){if(seconds===null||!Number.isFinite(seconds))return '—';const x=Math.floor(seconds);return `${Math.floor(x/3600)}h ${Math.floor(x%3600/60)}m ${x%60}s`;}
function percent(x){return x===null?'—':(x*100).toFixed(1)+'%';}
function health(){
  if(fetchError){$('connection').className='notice error';text('connection','状态连接异常：保留上次快照，未自动重跑或判定任务失败。');return;}
  if(!latest||latest.state==='NOT_CONNECTED'){$('connection').className='notice';text('connection','等待真实运行器接线。当前页面不是实验结果；刷新不会发起模型请求。');return;}
  const secs=age(latest.heartbeat_at);
  const stale=secs===null||secs>30;
  const idle=['COMPLETED','COMPLETED_WITH_GAPS','STOPPED'].includes(latest.state);
  $('connection').className=latest.over_request_cap?'notice error':(stale&&!idle?'notice warn':'notice ok');
  text('connection',latest.over_request_cap?'警告：记录的请求数已超本阶段上限，请查看真实账本。':stale&&!idle?'实验心跳未更新：数据可能陈旧，请查看本地进程。页面不会替你重发请求。':idle?'实验已结束；下面为最后保存的真实快照，仍须保留异常与未知。':'正在读取本地真实进度。指标仅对应已判分子集，不是完整阶段结论。');
  text('heartbeat',secs===null?'未提供':`${Math.floor(secs)}秒前`);
  const elapsed=latest.started_at?((idle&&latest.last_event_at?Date.parse(latest.last_event_at):Date.now())-Date.parse(latest.started_at))/1000:null;
  text('elapsed',duration(elapsed));
}
function rows(){
  const body=$('unit-rows');body.replaceChildren();
  let us=latest?latest.units:[];
  const filter=$('filter').value;
  us=us.filter(u=>filter==='all'||(filter==='attack'&&u.phase==='CORE'&&u.attack)||(filter==='clean'&&u.phase==='CORE'&&!u.attack)||(filter==='tech'&&u.phase==='TECH')||(filter==='active'&&['running','awaiting_judge'].includes(u.status))||(filter==='issues'&&['technical_error','response_unknown','blocked'].includes(u.status)));
  if(!us.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=7;td.textContent=latest&&latest.units.length?'此筛选下没有记录。':'等待真实任务账本；没有预填成功结果。';tr.append(td);body.append(tr);return;}
  for(const u of us){const tr=document.createElement('tr');const values=[u.eval_id,u.phase==='TECH'?'TECH':u.attack?'攻击':'正常',unitNames[u.status]||u.status,String(u.actor_turn),u.verdict||'—',matchNames[u.reference_match]||u.reference_match,u.error_code||'—'];values.forEach((v,i)=>{const td=document.createElement('td');td.textContent=v;if(i===4&&u.verdict)td.className='verdict '+u.verdict;if(i===2&&['technical_error','response_unknown','blocked'].includes(u.status))td.className='status-issue';tr.append(td);});body.append(tr);}
}
function render(s){
  latest=s;
  text('run-state',stateNames[s.state]||s.state);
  text('terminal',s.core.actor_terminal);text('judged',s.core.judged);
  $('exec-bar').value=s.core.actor_terminal;$('judge-bar').value=s.core.judged;
  text('judgment-detail',`待判分 ${s.core.awaiting_judge} · 技术异常 ${s.core.technical_error} · 响应未知 ${s.core.response_unknown}`);
  text('requests',s.requests.attempts);text('requests-detail',`已结算 ${s.requests.settled} · 在途 ${s.requests.in_flight} · 未知 ${s.requests.response_unknown}`);
  text('current-eval',s.current.eval_id||'—');text('current-role',`${roleNames[s.current.role]} · Actor轮数 ${s.current.actor_turn}`);
  text('tech',`技术验证：已登记 ${s.tech.registered}/4 · 执行终态 ${s.tech.actor_terminal}`);
  text('run-id',s.run_id||'未绑定');text('transport',s.transport);text('phase',phaseNames[s.phase]);text('updated',stamp(s.written_at));
  text('attack-n',`${s.attack.judged} / 26 已判分`);
  for(const [id,key] of [['attack-c','compromised'],['attack-p','partial'],['attack-s','safe']])text(id,s.attack.judged?s.attack[key]:'—');
  text('asr',s.attack.judged?`已判分子集 ASR：${percent(s.attack.observed_asr)}（${s.attack.compromised}/${s.attack.judged}）；剩余 ${26-s.attack.judged} 项没有有效判词。`:'尚无有效判分，ASR不填0。');
  text('clean-n',`${s.clean.judged} / 13 已判分`);text('clean-safe',s.clean.judged?s.clean.safe:'—');text('clean-denominator',` / ${s.clean.judged||'—'} Safe`);
  text('utility',s.clean.judged?`已判分子集原生Utility ${percent(s.clean.observed_safe_fraction)}；不等于业务真实完成率。`:'尚无有效判分；原生Safe不等于独立验证的业务完成。');
  rows();
  const eventList=$('events');eventList.replaceChildren();
  if(!s.events.length){const li=document.createElement('li');li.textContent='尚无运行器事件。';eventList.append(li);}
  for(const e of [...s.events].reverse()){const li=document.createElement('li');li.textContent=`${stamp(e.at)}  ${e.code}${e.unit_id?' · '+e.unit_id:''}`;eventList.append(li);}
  health();
}
async function poll(){
  if(busy)return;busy=true;const ctrl=new AbortController();const timer=setTimeout(()=>ctrl.abort(),1800);
  try{const response=await fetch('status.json',{cache:'no-store',signal:ctrl.signal});if(!response.ok)throw new Error('status unavailable');const data=await response.json();if(data.schema_version!==1)throw new Error('schema mismatch');fetchError=false;render(data);}
  catch(_e){fetchError=true;health();}finally{clearTimeout(timer);busy=false;}
}
$('filter').addEventListener('change',rows);
if(location.protocol==='file:'){fetchError=true;text('connection','请通过本地服务器打开此页面；直接双击HTML无法读取实时状态。');}
else{poll();setInterval(poll,2000);setInterval(health,1000);}
