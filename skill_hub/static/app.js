'use strict';
const $ = (s, root = document) => root.querySelector(s);
const csrf = $('meta[name="csrf-token"]').content;
const statusNames = {queued:'排队中',running:'更新中',success:'完成',partial:'部分完成',failed:'失败',interrupted:'未完成'};
const stages = ['Search','Read','Reason','Experiment','Write'];
const stageNames = {Search:'检索',Read:'阅读',Reason:'推理',Experiment:'实验',Write:'写作'};
let toastTimer;
function toast(message, error = false) {
  const t = $('#toast'); t.textContent = message; t.classList.toggle('error',error); t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.hidden = true, 6500);
}
function saved(message) { sessionStorage.setItem('skill-hub-notice',message); location.reload(); }
const savedNotice=sessionStorage.getItem('skill-hub-notice'); if(savedNotice){sessionStorage.removeItem('skill-hub-notice');toast(savedNotice);}
async function api(path, method = 'GET', body) {
  const response = await fetch(path,{method, headers: {'Content-Type':'application/json','X-CSRF-Token':csrf}, ...(body === undefined ? {} : {body:JSON.stringify(body)})});
  let data;
  try { data = await response.json(); } catch { throw new Error('服务响应异常，请确认本地应用仍在运行'); }
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '输入格式无效，请检查字段内容');
  return data;
}
function el(tag, text, cls) { const n = document.createElement(tag); if (text !== undefined) n.textContent=text; if(cls) n.className=cls; return n; }
function localTime(value) { return value ? new Date(value).toLocaleString(undefined,{hour12:false,timeZoneName:'short'}) : '—'; }
document.querySelectorAll('time[datetime]').forEach(n=>{if(n.dateTime) n.textContent=localTime(n.dateTime);});
const filters = $('#filters');
if(filters) filters.querySelectorAll('select,input[type="checkbox"]').forEach(n=>n.addEventListener('change',()=>filters.requestSubmit()));
let hadActive = false;
let pollBusy = false;
async function poll() {
  if(pollBusy || document.hidden) return;
  pollBusy = true;
  try {
    const runs = await api('/api/sync-runs');
    const active = runs.filter(r=>['queued','running'].includes(r.status));
    const status = $('#sync-status');
    if(active.length) { status.textContent=`${active.length} 个来源正在更新 · ${active.map(r=>`${r.source_name}：${statusNames[r.status]}（已处理 ${r.added+r.updated+r.skipped} / ${r.discovered}）`).join(' · ')}`; hadActive=true; }
    else if(hadActive && !$('#editor').open && !document.querySelector('.source-form[data-dirty]') && !document.querySelector('#filters:focus-within')) { location.reload(); return; }
    else if(runs.length) { const latest=new Map();runs.forEach(r=>{if(!latest.has(r.source_id))latest.set(r.source_id,r);});const attention=[...latest.values()].filter(r=>['partial','failed','interrupted'].includes(r.status)).length; status.textContent=`最近任务：${runs[0].source_name} · ${statusNames[runs[0].status]}${attention ? ` · ${attention} 个来源需关注，查看来源设置` : ''}`; }
    const table = $('#runs-body');
    if(table) {
      table.replaceChildren();
      if(!runs.length) { const row=el('tr'); const td=el('td','暂无刷新记录。首次采集会在后台开始，也可以点击刷新。'); td.colSpan=5; row.append(td); table.append(row); }
      runs.slice(0,30).forEach(r=>{const row=el('tr'); [r.source_name,statusNames[r.status],localTime(r.started_at),`${r.discovered} / ${r.added} / ${r.updated} / ${r.skipped} / ${r.failed}`,r.error || '—'].forEach(v=>row.append(el('td',v))); table.append(row);});
    }
  } catch(e) { $('#sync-status').textContent='无法读取更新状态；已显示的资料仍可查看。'; }
  finally { pollBusy=false; }
}
poll(); setInterval(poll,4000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden) poll();});
document.querySelectorAll('[data-refresh]').forEach(button=>button.addEventListener('click',async()=>{
  button.disabled=true;
  try { const result=await api('/api/refresh','POST',button.dataset.refresh==='all'?{}:{source_id:Number(button.dataset.refresh)});
    if(result.task_ids.length) { hadActive=true; toast(`已加入 ${result.task_ids.length} 个刷新任务${result.deferred.length ? '，部分来源正在等待重试' : ''}`); }
    else toast(result.deferred.map(d=>d.reason).join('；') || '没有启用的来源',true);
    await poll();
  } catch(e) { toast(e.message,true); } finally {button.disabled=false;}
}));
document.querySelectorAll('[data-favorite]').forEach(button=>button.addEventListener('click',async()=>{
  button.disabled=true;
  try { const favorite=button.dataset.value==='true'; await api(`/api/skills/${button.dataset.favorite}`,'PATCH',{favorite});
    button.textContent=favorite?'★':'☆'; button.dataset.value=String(!favorite); button.setAttribute('aria-pressed',String(favorite)); button.classList.toggle('is-favorite',favorite); button.setAttribute('aria-label',favorite?'取消收藏':'收藏'); toast(favorite?'已收藏':'已取消收藏');
  } catch(e) {toast(e.message,true);} finally {button.disabled=false;}
}));
function lines(text){return text.split('\n').map(s=>s.trim()).filter(Boolean);}
function evidence(text){return lines(text).map(line=>{const i=line.indexOf('|'); return i<0?{type:'待核实',url:line}:{type:line.slice(0,i).trim(),url:line.slice(i+1).trim()};});}
document.querySelectorAll('.source-form').forEach(form=>form.addEventListener('input',()=>form.dataset.dirty='true'));
document.querySelectorAll('.source-form').forEach(form=>form.addEventListener('submit',async event=>{
  event.preventDefault(); const submit=$('button[type="submit"]',form); submit.disabled=true;
  const values = new FormData(form);
  const payload={name:values.get('name'),repo:values.get('repo'),scan_roots:lines(values.get('scan_roots')),explicit_paths:lines(values.get('explicit_paths')),branch:values.get('branch'),refresh_interval_hours:Number(values.get('refresh_interval_hours')),enabled:values.has('enabled'),notes:values.get('notes'),evidence:evidence(values.get('evidence'))};
  try{ await api(form.dataset.source==='new'?'/api/sources':`/api/sources/${form.dataset.source}`,form.dataset.source==='new'?'POST':'PATCH',payload); saved('来源设置已保存'); }
  catch(e){toast(e.message,true);submit.disabled=false;}
}));
const dialog=$('#editor'); $('#close-editor').addEventListener('click',()=>dialog.close());
dialog.addEventListener('click',e=>{if(e.target===dialog && (e.clientX<dialog.getBoundingClientRect().left || e.clientX>dialog.getBoundingClientRect().right)) dialog.close();});
function select(options,value){const node=el('select');options.forEach(([v,t])=>{const o=el('option',t);o.value=v;node.append(o);});node.value=value??'';return node;}
async function openEditor(id){
  const content=$('#editor-content'); content.replaceChildren(el('p','正在读取条目…','muted')); $('#editor-title').textContent='条目详情'; if(!dialog.open) dialog.showModal();
  try{
    const s=await api(`/api/skills/${id}`); if(!dialog.open)return;
    $('#editor-title').textContent=s.name; content.replaceChildren();
    content.append(el('p',s.description_original,'detail-copy'));
    content.append(el('p',`所属仓库：${s.repo} · Skill 许可声明：${s.license || '未声明'} · 仓库许可：${s.repository_license || '未知'}`,'detail-metadata'));
    content.append(el('p',`解析状态：${s.parse_status==='success'?'成功':s.parse_status==='incomplete'?'元数据不完整':'待修复'} · 首次收录：${localTime(s.first_seen_at)} · 信息变化：${localTime(s.changed_at)}`,'detail-metadata'));
    if(s.warnings?.length) content.append(el('p',s.warnings.join('；'),'notice'));
    if(s.missing) content.append(el('p','暂未在上游目录找到；个人资料已保留。','notice'));
    if(s.requirements_excerpt) {content.append(el('h3','作者条件声明 · 短摘录'));content.append(el('p',s.requirements_excerpt,'detail-copy'));}
    content.append(el('p',`自动分类依据：${s.automatic.classification_reason}（${s.automatic.classification_version}）`,'detail-metadata'));
    const form=el('form',undefined,'edit-form'); const dirty=new Set(); const reset=new Set(); const inputs={};
    const choices=el('div',undefined,'inline-checks');
    ['favorite','featured'].forEach(k=>{const label=el('label',undefined,'check');const input=el('input');input.type='checkbox';input.checked=Boolean(s[k]);inputs[k]=input;label.append(input,document.createTextNode(k==='favorite'?'收藏':'精选（个人选择）'));choices.append(label);});form.append(choices);
    form.append(el('h3','人工整理'));
    form.append(el('p','只保存你修改过的字段。空白也会作为人工覆盖保留；“恢复自动”会清除该字段的覆盖。','field-note'));
    const stateChoices=[['unknown','未确认'],['required','必需'],['optional','可选'],['not_required','明确不需要']];
    const fields=[['primary_category','主分类','category'],['secondary_categories','辅助分类（逗号分隔：Search / Read / Reason / Experiment / Write）','list'],['summary_zh','中文简介','textarea'],['tags','中文能力标签（逗号分隔）','list'],['domain','领域','text'],['requirements_note','使用条件','textarea'],['api_key_status','API Key','state'],['paid_status','付费服务','state'],['out_of_scope','范围外','bool']];
    function display(input,type,v){if(type==='bool')input.checked=Boolean(v);else input.value=type==='list'?(v||[]).join(', '):(v??'');}
    for(const [key,title,type] of fields){
      const label=el('div',undefined,'edit-field'); const head=el('div',undefined,'override-heading'); const text=el('label',title+(Object.hasOwn(s.overrides,key)?' · 已覆盖':''));head.append(text);
      let input;
      if(type==='category')input=select([['','待分类'],...stages.map(c=>[c,`${stageNames[c]} · ${c}`])],s[key]);
      else if(type==='state')input=select(stateChoices,s[key]);
      else {input=el(type==='textarea'?'textarea':'input');if(type==='bool')input.type='checkbox';if(type==='textarea')input.rows=3;}
      display(input,type,s[key]);input.name=key;input.id=`edit-${key}`;text.htmlFor=input.id; inputs[key]={input,type};
      const restore=el('button','恢复自动','reset-field');restore.type='button';restore.addEventListener('click',()=>{reset.add(key);dirty.delete(key);display(input,type,s.automatic[key]);text.textContent=title+' · 保存后恢复自动';});head.append(restore);
      input.addEventListener('input',()=>{dirty.add(key);reset.delete(key);});input.addEventListener('change',()=>{dirty.add(key);reset.delete(key);});
      label.append(head,input);form.append(label);
    }
    const noteLabel=el('label','个人备注');const notes=el('textarea');notes.rows=3;notes.value=s.notes;noteLabel.append(notes);form.append(noteLabel);
    const evLabel=el('label','案例链接（每行：官方演示 / 作者报告 / 第三方案例 / 待核实 | URL）');const ev=el('textarea');ev.rows=2;ev.value=s.evidence.map(e=>`${e.type} | ${e.url}`).join('\n');evLabel.append(ev);form.append(evLabel);
    if(s.evidence.length){const links=el('div',undefined,'detail-metadata');s.evidence.forEach(e=>{try{const u=new URL(e.url);if(!['http:','https:'].includes(u.protocol)||u.username||u.password)return;const a=el('a',`${e.type} ↗ `);a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';links.append(a);}catch{}});form.append(links);}
    const submit=el('button','保存修改','primary');submit.type='submit';form.append(submit);
    form.addEventListener('submit',async event=>{event.preventDefault();submit.disabled=true;const overrides={};dirty.forEach(k=>{const {input,type}=inputs[k];overrides[k]=type==='bool'?input.checked:type==='list'?input.value.split(/[,，]/).map(x=>x.trim()).filter(Boolean):type==='category'?(input.value||null):input.value;});
      try{await api(`/api/skills/${id}`,'PATCH',{favorite:inputs.favorite.checked,featured:inputs.featured.checked,notes:notes.value,evidence:evidence(ev.value),overrides,clear_overrides:[...reset]});dialog.close();saved('修改已保存');}catch(e){toast(e.message,true);submit.disabled=false;}});
    content.append(form);
  }catch(e){content.replaceChildren(el('p',e.message,'notice'));}
}
document.querySelectorAll('[data-edit]').forEach(button=>button.addEventListener('click',()=>openEditor(button.dataset.edit)));
