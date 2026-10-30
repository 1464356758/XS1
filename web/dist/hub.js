import {GitHubClient,HubError,SYSTEM_REPOSITORY,parseRepository,safeBranch,blankRegistry,validateRegistry,validateChatURL,dayInShanghai,tomorrow,loadRegistry,saveRegistry,loadBook,readFormalChapter,encodeLocator,STATUS,newBookPrompt,writingPrompt,repairPrompt,checkerPrompt,randomId,validateReaderURL,validateLocalBackup,inspectExecution} from './hub-core.mjs';
import {AutoSync,mergeRegistries} from './auto-sync.mjs';
import {inspectTodayRegistry,selectionFingerprint,savedQuery,queryState,rememberQuery,QUERY_STATUS} from './today-query.mjs';
import {normalizeQueryHistory,mergeQueryHistory} from './query-model.mjs';
import {safeFilename,RequestGate} from './core.mjs';
import {progressKey,readingChapter,captureChapter,ExportJob,publicationStatus} from './reading-state.mjs';
import {matchesBook,filterBooks,pickBooks,filterChapters,bindSearch} from './search.mjs';
import {$,el,toast,localRead,localWrite,dateLabel,copyText,download,action,confirmAction} from './ui.mjs';

const CONFIG='novel-hub-config-v1',PRIVATE='novel-hub-private-v1',AUTH='novel-hub-auth-v1:';
let config=localRead(CONFIG,{});try{config={repository_url:parseRepository(config.repository_url||SYSTEM_REPOSITORY).url,branch:safeBranch(config.branch||'main')};}catch{config={repository_url:SYSTEM_REPOSITORY,branch:'main'};}
const legacy=localRead(PRIVATE,{chats:{},reader_url:''});
const spaceKey=()=> 'novel-hub-draft-v1:'+parseRepository(config.repository_url).key+':'+(config.branch||'default');
const authKey=()=>AUTH+parseRepository(config.repository_url).key;
function storedToken(){try{return sessionStorage.getItem(authKey())||localStorage.getItem(authKey())||'';}catch{return '';}}
function rememberCredential(token,remember){try{if(token)sessionStorage.setItem(authKey(),token);else sessionStorage.removeItem(authKey());if(remember&&token)localStorage.setItem(authKey(),token);else localStorage.removeItem(authKey());}catch{toast('授权未能保存在浏览器中，本次页面仍可同步。');}}
const state={registry:blankRegistry(),baseRegistry:null,baseFileHash:null,remoteLoaded:false,dirty:false,report:null,reportError:'',live:null,saving:false,checking:false,filter:'all',editing:null,client:new GitHubClient(config.repository_url,{token:storedToken()}),syncStatus:'loading',lastSaved:null,view:'dashboard'};
const draft=localRead(spaceKey(),null)||((!config.branch||config.branch==='main')?(localRead('novel-hub-draft-v1:'+parseRepository(config.repository_url).key+':default',null)||localRead('novel-hub-draft-v1:unbound:default',null)):null);
if(draft){try{state.registry=validateRegistry(draft.registry);state.baseFileHash=draft.baseFileHash||null;state.baseRegistry=draft.baseRegistry?validateRegistry(draft.baseRegistry):null;state.dirty=draft.dirty===true||!draft.baseRegistry;state.lastSaved=draft.lastSaved||null;}catch{toast('旧本机缓存格式异常，将读取 GitHub 清单。');}}
for(const book of state.registry.books)if(!book.chat_url&&legacy.chats?.[book.id]){try{book.chat_url=validateChatURL(legacy.chats[book.id]);state.dirty=true;}catch{}}
if(!state.registry.settings?.reader_url&&legacy.reader_url){try{state.registry.settings={reader_url:validateReaderURL(legacy.reader_url)};state.dirty=true;}catch{}}

function persist(){try{localWrite(spaceKey(),{registry:state.registry,baseRegistry:state.baseRegistry,baseFileHash:state.baseFileHash,dirty:state.dirty,lastSaved:state.lastSaved});}catch(e){notice(e.message,true);}}
function notice(message,error=false){$('globalNotice').hidden=!message;$('globalNotice').textContent=message;$('globalNotice').className='notice'+(error?' error':'');}
function ensureConnectionMutable(){if(sync.running||state.checking)throw new HubError('正在同步或查询，请完成后再修改连接。');}
const sync=new AutoSync({snapshot:()=>structuredClone(state.registry),canSave:()=>state.remoteLoaded&&state.client.canWrite,save:value=>saveRegistry(state.client,value,{branch:config.branch,baseFileHash:state.baseFileHash}),onCommit:(result,current)=>{
  state.baseFileHash=result.fileHash;state.baseRegistry=result.registry;state.lastSaved=result.registry.updated_at;
  state.registry=current?result.registry:{...state.registry,revision:result.registry.revision,updated_at:result.registry.updated_at};state.dirty=!current;persist();
},onStatus:(status,error)=>{state.syncStatus=status;state.saving=status==='saving';if(status==='error'){notice(error.message+' 修改已留在本机，请点击“重试同步”。',true);$('settingsStatus').textContent='保存未完成，请查看提示并重试同步。';}if(status==='saved'){notice('已自动保存到 GitHub。');$('settingsStatus').textContent='自动同步已启用，当前修改已保存并回读核对。';}if(status==='saving')$('settingsStatus').textContent='授权已启用，正在同步当前修改…';render();}});
function changed(){state.registry=validateRegistry(state.registry);state.dirty=true;persist();sync.touch();render();}
const labels={newBook:['新书指令','开始一本新书。','填入独立新书仓库，复制指令，连同初始化包发给新的 GPT 工作聊天。'],dashboard:['我的小说','我的小说。','点击书名看正文，新增和修改自动保存到 GitHub。'],prompts:['日更指令','每天，接着写。','选一本小说和执行时间，生成完整指令，复制到对应 GPT 工作聊天。'],reading:['阅读正文','接着读下去。','从已加入的小说中选择，直接阅读、复制和导出。'],delivery:['小说代发码','选择小说，就有代发码。','把代发链接交给合作人，文章随仓库更新。'],reports:['今日更新','查询今天更新。','勾选小说，点击查询，按最新章节的提交日期判断。'],settings:['同步设置','一次授权，自动保存。','GitHub 保存清单与设置，打开软件自动读取。']};
function setView(name,open=true){if(!labels[name])return;state.view=name;for(const key of Object.keys(labels))$(key+'View').hidden=key!==name;document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===name));$('viewLabel').textContent=labels[name][0];$('pageTitle').textContent=labels[name][1];$('pageSubtitle').textContent=labels[name][2];if(name==='delivery')generateCode();if(name==='prompts')updateWritingPrompt();if(name==='newBook')updateNewBookPrompt();if(name==='reading'&&open){const b=selectedBook('readBookSelect');if(b&&reading?.entry.id!==b.id)openReader(b);}}
function selectedBook(id){return state.registry.books.find(b=>b.id===$(id).value);}
function showText(title,text){$('textTitle').textContent=title;$('textContent').value=text;$('textDialog').showModal();}
document.querySelectorAll('[data-view]').forEach(b=>action(b,()=>setView(b.dataset.view)));
document.querySelectorAll('[data-close]').forEach(b=>action(b,()=>$(b.dataset.close).close()));
for(const id of ['connectionLabel','authorizeSync'])action($(id),()=>{setView('settings');$('writeToken').focus();});
const badge=status=>el('span','badge '+(status||'unknown'),QUERY_STATUS[status]||STATUS[status]||'待读取');
let renderSeq=0,optionSignature='',promptBookId='';
const pickers=[['deliveryBook','deliveryBook'],['readBookSelect','readingBook'],['writingBook','writingBook']],pickerChoices=new Map();
function renderOptions({force=false}={}){
  const signature=JSON.stringify([state.registry.books.map(b=>[b.id,b.title,b.expected_time,b.chat_url||'',b.feedback_url||'',b.repository_url,b.branch]),pickers.map(([,prefix])=>$(prefix+'Search').value)]);if(signature===optionSignature&&!force)return;optionSignature=signature;
  for(const [id,prefix] of pickers){
    const select=$(id),old=select.value||pickerChoices.get(id)||'',query=$(prefix+'Search').value,{matches,selectedId}=pickBooks(state.registry.books,query,old);
    if(select.value)pickerChoices.set(id,select.value);select.replaceChildren();
    if(!selectedId){const o=el('option',null,!state.registry.books.length?'先添加一部小说':!matches.length?'没有匹配的小说':'请选择匹配的小说');o.value='';o.disabled=true;select.append(o);}
    for(const book of matches){const o=el('option',null,book.title+' · '+parseRepository(book.repository_url).name);o.value=book.id;select.append(o);}
    select.value=selectedId;select.disabled=!matches.length;if(selectedId)pickerChoices.set(id,selectedId);
    $(prefix+'Status').textContent='显示 '+matches.length+' / '+state.registry.books.length+' 部'+(matches.length&&!selectedId?' · 请从结果中选择一本':'');
  }
  $('readRefresh').disabled=!selectedBook('readBookSelect');generateCode();updateWritingPrompt();
}
function chooseBook(id,book){
  const prefix=pickers.find(([key])=>key===id)[1];if(!matchesBook(book,$(prefix+'Search').value)){$(prefix+'Search').value='';$(prefix+'Clear').hidden=true;}
  $(id).value=book.id;pickerChoices.set(id,book.id);renderOptions({force:true});$(id).value=book.id;
}
for(const [id,prefix] of pickers){bindSearch({input:$(prefix+'Search'),clear:$(prefix+'Clear'),onChange:renderOptions});$(id).addEventListener('change',()=>{if($(id).value)pickerChoices.set(id,$(id).value);renderOptions({force:true});});}

async function render(){
  const seq=++renderSeq,registry=state.registry,fp=await selectionFingerprint(registry);if(seq!==renderSeq)return;
  const liveGood=state.live?.date===dayInShanghai()&&state.live.selection_fingerprint===fp,shown=state.live||state.report,report=await queryState(shown,registry);if(seq!==renderSeq)return;
  const current=liveGood?state.live:report.fresh&&!state.reportError?shown:null,results=new Map((current?.results||[]).map(r=>[r.id,r]));
  $('selectedCount').replaceChildren(document.createTextNode(registry.books.filter(b=>b.enabled).length),el('small',null,'部'));
  $('updatedCount').textContent=current?current.results.filter(r=>r.status==='updated').length:'—';$('attentionCount').textContent=current?current.results.filter(r=>['not_updated','empty'].includes(r.status)).length:'—';$('updatedHint').textContent=current?.complete===false?'正在逐本核对':liveGood?'刚刚核对仓库':report.fresh?'今天上次查询结果':'点击查询即可查看';$('latestCheck').textContent=current?dateLabel(current.checked_at,true):'—';$('reportFreshness').textContent=report.label;
  const canWrite=state.client.canWrite;
  $('connectionLabel').textContent=state.saving?'正在自动保存…':state.dirty?(state.syncStatus==='error'?'同步失败 · 查看设置':canWrite?'有修改待同步':'启用 GitHub 自动保存'):state.remoteLoaded?'GitHub 已连接':state.syncStatus==='error'?'GitHub 连接失败 · 重试':'正在读取 GitHub…';
  $('saveIndicator').textContent=state.saving?'● 正在自动保存':state.dirty?(state.syncStatus==='error'?'● 保存未完成':canWrite?'● 等待自动同步':'● 待授权保存'):state.lastSaved?'● GitHub 已保存 '+dateLabel(state.lastSaved):state.remoteLoaded?'● GitHub 已读取':'● 尚未读取 GitHub';$('saveIndicator').classList.toggle('dirty',state.dirty);
  $('saveHint').textContent=state.dirty&&!canWrite?'授权后会自动保存当前修改，无需重新添加小说。':'新增、编辑、勾选都会自动同步；再次打开读取 GitHub。';$('retrySync').hidden=state.syncStatus!=='error';$('retrySync').disabled=state.saving;$('authorizeSync').hidden=canWrite;
  $('bookRows').replaceChildren();const q=$('bookSearch').value;let visible=0;
  for(const book of registry.books){
    const result=!book.enabled?{status:'paused',reason:'不参与检查'}:results.get(book.id);if(!matchesBook(book,q))continue;if(state.filter==='enabled'&&!book.enabled)continue;if(state.filter==='attention'&&!['not_updated','empty','unknown'].includes(result?.status))continue;
    visible++;const row=el('tr'),td=el('td'),check=el('input');td.dataset.label='参与查询';check.type='checkbox';check.checked=book.enabled;check.setAttribute('aria-label','检查《'+book.title+'》');check.addEventListener('change',()=>{state.registry.books=state.registry.books.map(b=>b.id===book.id?{...b,enabled:check.checked}:b);changed();});td.append(check);row.append(td);
    const titleTd=el('td'),cell=el('div','book-cell'),title=el('button','book-open book-title',book.title);action(title,()=>openReader(book));const words=el('div');words.append(title,el('span','book-meta',Number.isInteger(result?.chapter)?result.chapter+' 章':book.baseline?'接入时 '+book.baseline.chapter_count+' 章 · 待查询':'待读取章节'));cell.append(el('span','book-avatar',book.title.slice(0,1)),words);titleTd.append(cell);row.append(titleTd);
    const time=el('td');time.dataset.label='写作计划';time.append(el('div',null,book.expected_time),el('span','book-meta','北京时间'));row.append(time);const statusTd=el('td');statusTd.dataset.label='今天更新';statusTd.append(badge(result?.status),el('span','status-note',result?.reason||'尚无今日检查结果'));row.append(statusTd);
    const actionsTd=el('td'),actions=el('div','row-actions');for(const [label,fn] of [['查看正文',()=>openReader(book)],['代发码',()=>{setView('delivery');chooseBook('deliveryBook',book);generateCode();}],['日更指令',()=>openWritingPrompt(book)],['编辑',()=>openBookDialog(book)]]){const button=el('button',null,label);action(button,fn);actions.append(button);}
    const menu=el('select');menu.setAttribute('aria-label','《'+book.title+'》更多操作');for(const [value,label] of [['','更多'],['chat','打开任务 / GPT'],['schedule','定时指令'],['repair','补更指令'],['remove','移出清单']]){const o=el('option',null,label);o.value=value;menu.append(o);}menu.addEventListener('change',()=>{const value=menu.value;menu.value='';bookAction(book,value).catch(e=>toast(e.message));});actions.append(menu);actionsTd.append(actions);row.append(actionsTd);$('bookRows').append(row);
  }
  $('booksEmpty').hidden=registry.books.length>0;$('booksNoMatch').hidden=!registry.books.length||visible>0;$('bookSearchStatus').textContent='显示 '+visible+' / '+registry.books.length+' 部 · 搜索不改变查询勾选范围';renderOptions();renderReports(report,shown);$('checkReportNow').disabled=$('checkNow').disabled=state.checking||!registry.books.some(b=>b.enabled);$('exportReport').disabled=state.checking||!shown||shown.complete===false;
}
function renderReports(info,report){
  $('reportMeta').textContent=report?'查询时间 '+dateLabel(report.checked_at)+' · 共 '+report.results.length+' 部小说':'尚未查询';
  const latest=report?.date===dayInShanghai();
  const saved=state.baseRegistry?.query_history?.some(q=>q.checked_at===report?.checked_at&&q.selection_fingerprint===report?.selection_fingerprint);
  $('reportNotice').textContent=state.checking?'正在逐本读取最新章节，请稍候…':!report?'勾选小说后点击“查询今天更新”，不限查询时间，不需要先生成日报。':!latest?'这里是 '+report.date+' 的历史结果，点击查询可查看今天。':info.fresh?'按最新章节最近一次提交日期（北京时间）判断。'+(saved?'查询记录已同步。':state.syncStatus==='error'?'查询已完成，GitHub 保存未完成，请重试同步。':state.client.canWrite?'查询已完成，等待保存到 GitHub。':'查询结果已保留在本机；启用自动同步后可保存到 GitHub。'):info.label;
  $('reportNotice').className='notice';$('reportResults').replaceChildren();
  const results=filterBooks(report?.results||[],$('reportSearch').value);$('reportSearchControls').hidden=!report;$('reportSearchStatus').textContent='显示 '+results.length+' / '+(report?.results.length||0)+' 条 · 查询范围保持全部已勾选小说';$('reportNoMatch').hidden=!report||results.length>0;
  for(const r of results){const card=el('article','card report-item'),text=el('div');text.append(el('h3',null,r.title));if(r.chapter!==null&&r.chapter!==undefined)text.append(el('p',null,r.chapter?'最新第'+r.chapter+'章'+(r.chapter_title?'《'+r.chapter_title+'》':''):'暂无正式章节'));if(r.latest_change_at)text.append(el('p',null,'章节更新：'+new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(r.latest_change_at))));text.append(el('p',null,r.reason||''));if(r.delta==='new_chapter')text.append(el('small',null,'相比上次成功查询，已新增章节'));else if(r.delta==='revised')text.append(el('small',null,'相比上次成功查询，章节内容已修改'));card.append(text,badge(r.status));$('reportResults').append(card);}
}
async function readReport(){state.report=savedQuery(state.registry);if(!state.checking)state.live=null;state.reportError='';await render();}
const queryCacheKey=()=> 'novel-hub-query-cache-v2:'+parseRepository(config.repository_url).key+':'+(config.branch||'default');
function queryCache(){try{return normalizeQueryHistory(localRead(queryCacheKey(),null)||((!config.branch||config.branch==='main')?localRead('novel-hub-query-cache-v1:'+parseRepository(config.repository_url).key,[]):[]));}catch{return [];}}

function payload(registry){return JSON.stringify({books:registry.books,settings:registry.settings||{},query_history:registry.query_history||[]});}
async function readRemote({initial=false,replace=false}={}){
  if(sync.running)return;const remote=await loadRegistry(state.client,config.branch);config.branch=remote.branch;localWrite(CONFIG,config);
  if(state.dirty&&!replace){
    if(payload(remote.registry)===payload(state.registry)){state.registry=remote.registry;state.dirty=false;sync.acknowledge();}
    else if(state.baseFileHash!==remote.fileHash){
      const merged=mergeRegistries(remote.registry,state.registry,state.baseRegistry);
      if(merged.conflicts.length){state.remoteLoaded=true;state.syncStatus='error';throw new HubError('GitHub 与本机有同一本书的不同修改。请先导出备份，再刷新选择需要的版本。','conflict');}
      state.registry=validateRegistry(merged.registry);state.dirty=payload(state.registry)!==payload(remote.registry);if(!state.dirty)sync.acknowledge();
    }
  }else{state.registry=remote.registry;state.dirty=false;sync.acknowledge();}
  state.baseFileHash=remote.fileHash;state.baseRegistry=remote.registry;state.remoteLoaded=true;state.lastSaved=remote.registry.updated_at;
  const history=mergeQueryHistory(state.registry.query_history||[],queryCache());if(JSON.stringify(history)!==JSON.stringify(state.registry.query_history||[])){state.registry={...state.registry,query_history:history};if(state.client.canWrite)state.dirty=true;}persist();
  $('readerBase').value=state.registry.settings?.reader_url||legacy.reader_url||new URL('reader.html',location.href).href;
  if(state.dirty){if(!sync.dirty)sync.touch();if(initial||state.client.canWrite)sync.flush();}else state.syncStatus='saved';
  $('useDefaultRegistry').hidden=!remote.missing||parseRepository(config.repository_url).key===parseRepository(SYSTEM_REPOSITORY).key;
  if(remote.missing)notice('已连接 '+parseRepository(config.repository_url).name+'，此仓库还没有管理清单。小说仓库链接应在“添加小说”中填写。');else if(!state.dirty&&!sync.fault)notice('');
  await render();await readReport();
}
action($('loadRemote'),async()=>{if(state.dirty&&!await confirmAction('本机有尚未同步的修改。是否采用 GitHub 版本替换？取消可先导出备份。'))return;await readRemote({replace:true});toast('已读取 GitHub 最新清单。');});
action($('retrySync'),async()=>{try{await readRemote();if(state.dirty)await sync.retry();}catch(e){notice(e.message,true);}});
action($('refreshReport'),()=>readRemote());
action($('checkReportNow'),()=>runTodayQuery());
action($('useDefaultRegistry'),async()=>{
  ensureConnectionMutable();const client=new GitHubClient(SYSTEM_REPOSITORY),remote=await loadRegistry(client,'main'),merged=mergeRegistries(remote.registry,state.registry);
  if(merged.conflicts.length)throw new HubError('默认清单与本机同一本书的设置不同，请先导出备份再核对。');
  if(state.dirty)localWrite(spaceKey(),{registry:state.registry,baseRegistry:state.baseRegistry,baseFileHash:state.baseFileHash,dirty:true,lastSaved:state.lastSaved});
  state.client.clearToken();config={repository_url:SYSTEM_REPOSITORY,branch:'main'};localWrite(CONFIG,config);state.client=new GitHubClient(config.repository_url,{token:storedToken()});state.registry=validateRegistry(merged.registry);state.baseRegistry=remote.registry;state.baseFileHash=remote.fileHash;state.remoteLoaded=true;state.lastSaved=remote.registry.updated_at;sync.acknowledge();state.dirty=payload(state.registry)!==payload(remote.registry);if(state.dirty)sync.touch();persist();$('managementRepo').value=config.repository_url;$('managementBranch').value=config.branch;$('useDefaultRegistry').hidden=true;notice('已读取默认管理仓库，原仓库的本机草稿仍保留。');await render();await readReport();
});
async function runTodayQuery(){
  if(state.checking)return;if(!state.registry.books.some(b=>b.enabled))throw new HubError('先勾选需要查询的小说。');
  state.checking=true;$('exportReport').disabled=true;setView('reports');for(const id of ['checkNow','checkReportNow'])$(id).disabled=true;const registry=structuredClone(state.registry),started=new Date();
  try{const fingerprint=await selectionFingerprint(registry);state.live=null;
    const result=await inspectTodayRegistry(registry,{now:started,onProgress:(n,total,item,partial)=>{
      $('checkReportNow').textContent='查询中 '+n+'/'+total;state.live={schema_version:1,type:'novel-today-query-v1',date:dayInShanghai(started),checked_at:started.toISOString(),selection_fingerprint:fingerprint,results:partial,counts:{},complete:false};render();
    }});
    state.live=result;state.registry=validateRegistry(rememberQuery(state.registry,result));try{localWrite(queryCacheKey(),state.registry.query_history);}catch(e){notice('查询已完成，但本机记录未能保存：'+e.message,true);}
    if(state.client.canWrite&&state.remoteLoaded)changed();else persist();await render();
  }finally{state.checking=false;$('checkNow').disabled=false;$('checkReportNow').disabled=false;$('checkNow').textContent=$('checkReportNow').textContent='查询今天更新';await render();}
}
action($('checkNow'),runTodayQuery);
bindSearch({input:$('bookSearch'),clear:$('bookClear'),onChange:render});bindSearch({input:$('reportSearch'),clear:$('reportClear'),onChange:render});
action($('resetBookSearch'),()=>{$('bookSearch').value='';$('bookClear').hidden=true;state.filter='all';document.querySelectorAll('[data-filter]').forEach(button=>button.classList.toggle('selected',button.dataset.filter==='all'));render();});document.querySelectorAll('[data-filter]').forEach(b=>action(b,()=>{state.filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('selected',x===b));render();}));
function openBookDialog(book=null){state.editing=book?.id||null;$('bookForm').reset();$('bookDialogTitle').textContent=book?'编辑小说':'添加小说';$('bookRepo').value=book?.repository_url||'';$('bookName').value=book?.title||'';$('bookBranch').value=book?.branch||'';$('bookChat').value=book?.chat_url||legacy.chats?.[book?.id]||'';$('bookFeedback').value=book?.feedback_url||'';$('bookTime').value=book?.expected_time||'09:00';$('bookGrace').value=book?.grace_minutes??60;$('bookStart').value=book?.effective_from||tomorrow();$('bookEnabled').checked=book?.enabled??true;$('submitBook').textContent=book?'保存修改':'添加并打开正文';$('bookFormError').hidden=true;$('bookDialog').showModal();}
for(const id of ['addBook','emptyAdd'])action($(id),()=>openBookDialog());
const addGate=new RequestGate();$('bookDialog').addEventListener('close',()=>addGate.cancel());
$('bookForm').addEventListener('submit',async event=>{
  event.preventDefault();const ticket=addGate.start();$('submitBook').disabled=true;$('submitBook').textContent='读取小说中…';$('bookFormError').hidden=true;
  try{const repo=parseRepository($('bookRepo').value),branch=safeBranch($('bookBranch').value),chat=validateChatURL($('bookChat').value),feedback=validateChatURL($('bookFeedback').value),client=new GitHubClient(repo.url),book=await loadBook(client,branch);if(!ticket.current())return;
    const prior=state.registry.books.find(b=>b.id===state.editing);if(prior?.book_id&&prior.book_id!==book.manifest.book.id)throw new HubError('这不是原来的小说，请单独添加。');
    const entry={id:prior?.id||randomId(),book_id:book.manifest.book.id,title:$('bookName').value.trim()||book.manifest.book.title,repository_url:repo.url,branch,enabled:$('bookEnabled').checked,expected_time:$('bookTime').value,grace_minutes:Number($('bookGrace').value),effective_from:$('bookStart').value,baseline:prior?.baseline||{chapter_count:book.manifest.chapters.length,commit:book.snapshot.commit,captured_at:new Date().toISOString()},...(chat?{chat_url:chat}:{}),...(feedback?{feedback_url:feedback}:{})};
    state.registry=validateRegistry({...state.registry,books:prior?state.registry.books.map(b=>b.id===prior.id?entry:b):[...state.registry.books,entry]});changed();$('bookDialog').close();await openReader(entry,{client,book});toast(state.client.canWrite?'已加入，正在自动保存到 GitHub。':'已加入并打开正文；启用自动保存后会同步到 GitHub。');
  }catch(e){if(ticket.current()){$('bookFormError').textContent=e.message;$('bookFormError').hidden=false;}}finally{$('submitBook').disabled=false;$('submitBook').textContent='添加并打开正文';}
});
async function bookAction(book,value){if(value==='chat'){const url=validateChatURL(book.feedback_url||book.chat_url||legacy.chats?.[book.id]||'');if(!url){openBookDialog(book);return;}window.open(url,'_blank','noopener,noreferrer');}if(value==='schedule')openWritingPrompt(book);if(value==='repair')showText('补更指令',repairPrompt(book));if(value==='remove'&&await confirmAction('把《'+book.title+'》移出小说清单？不会删除仓库或正文。')){state.registry.books=state.registry.books.filter(b=>b.id!==book.id);changed();if(reading?.entry.id===book.id){exports.cancel();reading=null;readTicket++;chapterTicket++;$('readText').textContent='';$('readPublication').textContent='';$('readTitle').textContent='这部小说已移出清单';disableReading();}}}
function updateNewBookPrompt(){
  let text='',error='';const repository=$('newBookRepo').value.trim();
  if(repository)try{text=newBookPrompt({repository,platform:$('newBookPlatform').value,preferences:$('newBookPreferences').value,management:config.repository_url});}catch(e){error=e.message;}
  $('newBookPromptText').value=text;$('generateNewBookPrompt').disabled=$('copyNewBookPrompt').disabled=!text;
  $('newBookPromptStatus').textContent=error|| (text?'指令已生成。复制后与初始化包一起发送。':'先填写这本新书的 GitHub 仓库链接。');
  $('newBookRepo').setCustomValidity(error);return text;
}
async function copyNewBookPrompt(){const text=updateNewBookPrompt();if(!text){$('newBookRepo').reportValidity();return;}try{await copyText(text);$('newBookPromptStatus').textContent='已复制。请在新的 GPT 工作聊天中附加初始化包，再粘贴发送。';toast('新书指令已复制。');}catch(e){$('newBookPromptStatus').textContent='指令已生成，请在预览框中长按选中并复制。';throw e;}}
action($('openNewBookPrompt'),()=>{setView('newBook');$('newBookRepo').focus();});
for(const id of ['newBookRepo','newBookPreferences'])$(id).addEventListener('input',updateNewBookPrompt);
$('newBookPlatform').addEventListener('change',updateNewBookPrompt);
$('newBookPromptForm').addEventListener('submit',event=>{event.preventDefault();copyNewBookPrompt().catch(e=>toast(e.message));});
action($('copyNewBookPrompt'),copyNewBookPrompt);
function updateWritingPrompt({resetTime=false}={}){
  const book=selectedBook('writingBook'),changedBook=(book?.id||'')!==promptBookId;
  if(book&&(changedBook||resetTime))$('writingTime').value=book.expected_time||'09:00';
  promptBookId=book?.id||'';
  const time=$('writingTime').value,valid=!!book&&/^([01]\d|2[0-3]):[0-5]\d$/.test(time);
  const text=valid?writingPrompt({...book,expected_time:time},config.repository_url):'';
  if($('writingPromptText').value!==text){$('writingPromptStatus').textContent='';executionTicket++;$('executionStatus').textContent='';$('checkExecution').disabled=!book;}
  $('writingPromptText').value=text;$('writingPromptTitle').textContent=book?'《'+book.title+'》日更指令':'完整日更指令';
  $('writingPromptSummary').textContent=book?(valid?'每天北京时间 '+time+' · 每次只写一章':'请选择有效的每天执行时间。'):(state.registry.books.length?'请从搜索结果中选择小说。':'先在“我的小说”添加一本书。');
  $('generateWritingPrompt').disabled=$('copyWritingPrompt').disabled=!valid;
  const chat=book?.feedback_url||book?.chat_url||legacy.chats?.[book?.id]||'';$('openWritingChat').disabled=!chat;$('checkExecution').disabled=!book||executionBusy;
  $('writingChatHint').textContent=book?.feedback_url?'已登记固定反馈对话。后续复用同一个任务，任务绑定以 GPT 实际显示为准。':chat?'复制后打开本书聊天，粘贴发送；已有任务就更新，不重复创建。':book?'可在“我的小说 → 编辑”填写 GPT 或固定任务反馈链接；也可自行打开对应聊天。':'';
  return text;
}
function openWritingPrompt(book=null){setView('prompts');if(book){chooseBook('writingBook',book);updateWritingPrompt({resetTime:true});}}
async function copyWritingPrompt(){const text=updateWritingPrompt();if(!text)throw new HubError('请先选择小说和有效执行时间。');try{await copyText(text);$('writingPromptStatus').textContent='已复制完整指令，请到本书 GPT 工作聊天粘贴并发送。';toast('日更指令已复制。');}catch(e){$('writingPromptStatus').textContent='完整指令已生成，请在预览框中长按选中并复制。';throw e;}}
action($('openWritingPrompt'),()=>openWritingPrompt());
$('writingBook').addEventListener('change',()=>updateWritingPrompt({resetTime:true}));$('writingTime').addEventListener('input',()=>updateWritingPrompt());
$('writingPromptForm').addEventListener('submit',event=>{event.preventDefault();copyWritingPrompt().catch(e=>toast(e.message));});
action($('copyWritingPrompt'),copyWritingPrompt);
action($('openWritingChat'),()=>{const book=selectedBook('writingBook');if(book)return bookAction(book,'chat');});
let executionTicket=0,executionBusy=false;
action($('checkExecution'),async()=>{const book=selectedBook('writingBook');if(!book)throw new HubError('先添加小说。');const ticket=++executionTicket;executionBusy=true;$('checkExecution').disabled=true;$('executionStatus').textContent='正在读取 GitHub 完成证据…';try{const result=await inspectExecution(book);if(ticket!==executionTicket||selectedBook('writingBook')?.id!==book.id)return;$('executionStatus').textContent=result.label+'。'+result.reason+(result.commit?' 来源提交 '+result.commit.slice(0,9)+'。':'');}finally{executionBusy=false;$('checkExecution').disabled=!selectedBook('writingBook');}});
action($('copyChecker'),()=>showText('每天20:00总检查任务',checkerPrompt(config.repository_url,config.branch)));action($('textCopy'),async()=>{await copyText($('textContent').value);toast('已复制。');});

let reading=null,readTicket=0,chapterTicket=0;const exports=new ExportJob();
const readKey=current=>progressKey(current.client.repo.key,current.book.snapshot.branch,current.book.manifest.book.id);
function disableReading(){for(const id of ['readCopy','readExport','readPrev','readNext','readExportAll'])$(id).disabled=true;}
async function openReader(entry,loaded=null){
  chooseBook('readBookSelect',entry);setView('reading',false);const ticket=++readTicket;chapterTicket++;exports.cancel();reading=null;disableReading();$('readExportAll').textContent='导出整本';$('readBookTitle').textContent=entry.title;$('readTitle').textContent='读取目录中…';$('readMeta').textContent='';$('readStatus').textContent='';$('readText').textContent='';$('readPublication').textContent='';$('readChapterSearch').value='';$('readChapterClear').hidden=true;renderChapters();
  try{const client=loaded?.client||new GitHubClient(entry.repository_url),book=loaded?.book||await loadBook(client,entry.branch);if(ticket!==readTicket)return;if(entry.book_id&&entry.book_id!==book.manifest.book.id)throw new HubError('作品身份已改变，请核对仓库。');reading={client,book,entry,chapter:null,text:null};$('readBookTitle').textContent=book.manifest.book.title;$('readMeta').textContent=book.manifest.chapters.length+'章 · 最新提交 '+book.snapshot.commit.slice(0,9);renderChapters();if(book.manifest.chapters.length){$('readExportAll').disabled=false;await readChapter(readingChapter(book.manifest.chapters,localRead(readKey(reading),null)));}else{$('readTitle').textContent='还没有正式章节';$('readStatus').textContent='等待 GPT 完成创作和采用正文。';}}
  catch(e){if(ticket===readTicket){$('readTitle').textContent='暂时无法读取正文';$('readStatus').textContent=e.message;}}
}
$('readBookSelect').addEventListener('change',()=>{const b=selectedBook('readBookSelect');if(b)openReader(b);});action($('readRefresh'),()=>{const b=selectedBook('readBookSelect');if(b)return openReader(b);throw new HubError('先添加小说。');});
function renderChapters(){
  const chapters=reading?.book.manifest.chapters||[],matches=filterChapters(chapters,$('readChapterSearch').value);$('readChapters').replaceChildren();$('readChapterSearch').disabled=!chapters.length;$('readChapterStatus').textContent='显示 '+matches.length+' / '+chapters.length+' 章';$('readChapterEmpty').hidden=!reading||matches.length>0;
  for(const c of matches){const b=el('button','chapter-choice'+(reading.chapter?.number===c.number?' active':''),'第'+c.number+'章 '+c.title);action(b,()=>readChapter(c));$('readChapters').append(b);}
}
bindSearch({input:$('readChapterSearch'),clear:$('readChapterClear'),onChange:renderChapters});

async function readChapter(chapter){const current=reading;if(!current)return;const ticket=++chapterTicket;current.text=null;current.chapter=chapter;disableReading();$('readTitle').textContent='第'+chapter.number+'章 '+chapter.title;$('readStatus').textContent='正在校验正文…';$('readText').textContent='';$('readPublication').textContent='';renderChapters();try{const text=await readFormalChapter(current.client,current.book,chapter);if(reading!==current||ticket!==chapterTicket)return;current.text=text;$('readText').textContent=text;$('readStatus').textContent=chapter.han_count+'汉字 · 正文校验通过';$('readPublication').textContent=publicationStatus(current.book.state,chapter);$('readCopy').disabled=false;$('readExport').disabled=false;$('readExportAll').disabled=exports.active?.owner===current;$('readPrev').disabled=chapter.number===1;$('readNext').disabled=chapter.number===current.book.manifest.chapters.length;try{const p=captureChapter(current,chapter,text);localWrite(readKey(current),{chapter:p.chapter,sha256:p.sha256,at:p.at});}catch{$('readStatus').textContent+=' · 本机未能记住阅读位置';}}catch(e){if(ticket===chapterTicket)$('readStatus').textContent=e.message;}}
const chapterOutput=()=>{if(!reading||reading.text===null)throw new HubError('正文尚未读取并核验。');return '第'+reading.chapter.number+'章 '+reading.chapter.title+'\n\n'+reading.text;};
action($('readCopy'),async()=>{await copyText(chapterOutput());toast('整章已复制。');});action($('readExport'),()=>download(chapterOutput(),safeFilename(reading.entry.title+'_第'+reading.chapter.number+'章')));
for(const [id,step] of [['readPrev',-1],['readNext',1]])action($(id),()=>{const c=reading?.book.manifest.chapters[(reading.chapter?.number||0)-1+step];if(c)return readChapter(c);});
action($('readExportAll'),async()=>{const current=reading;if(!current?.book.manifest.chapters.length)throw new HubError('没有正式章节。');const job=exports.start(current);$('readExportAll').disabled=true;try{const output=[];for(const c of current.book.manifest.chapters){if(reading!==current||!exports.current(job))return;$('readExportAll').textContent='核对 '+c.number+'/'+current.book.manifest.chapters.length;const text=await readFormalChapter(current.client,current.book,c);if(!exports.current(job)||reading!==current)return;output.push('第'+c.number+'章 '+c.title+'\n\n'+text);}if(exports.current(job)&&reading===current)download(current.book.manifest.book.title+'\n\n'+output.join('\n\n'),safeFilename(current.book.manifest.book.title));}catch(e){if(exports.current(job)&&reading===current)throw e;}finally{const visible=exports.current(job)&&reading===current;exports.finish(job);if(visible){$('readExportAll').disabled=!reading?.text;$('readExportAll').textContent='导出整本';}}});

let codeTicket=0;
async function generateCode(){const ticket=++codeTicket,book=selectedBook('deliveryBook');$('deliveryCode').value='';$('copyCode').disabled=$('copyShareLink').disabled=!book;if(!book)return '';const code=await encodeLocator(book);if(ticket!==codeTicket||selectedBook('deliveryBook')?.id!==book.id)return '';$('deliveryCode').value=code;return code;}
$('deliveryBook').addEventListener('change',generateCode);action($('copyCode'),async()=>{const code=await generateCode();if(!code)throw new HubError('先添加并选择小说。');await copyText(code);toast('代发码已复制。');});
function readerURL(){return validateReaderURL(state.registry.settings?.reader_url||legacy.reader_url||new URL('reader.html',location.href).href);}
action($('copyShareLink'),async()=>{const code=await generateCode();if(!code)throw new HubError('先选择小说。');await copyText(readerURL()+'#'+code);toast('代发链接已复制。');});
action($('saveReaderBase'),()=>{state.registry.settings={reader_url:validateReaderURL($('readerBase').value.trim())};changed();toast('代发网址已修改，正在自动同步。');});

$('managementRepo').value=config.repository_url;$('managementBranch').value=config.branch;try{$('rememberToken').checked=!!localStorage.getItem(authKey());}catch{}
$('settingsForm').addEventListener('submit',async event=>{
  event.preventDefault();try{ensureConnectionMutable();const next={repository_url:parseRepository($('managementRepo').value).url,branch:safeBranch($('managementBranch').value)},different=next.repository_url!==config.repository_url||next.branch!==config.branch,token=$('writeToken').value.trim()||(!different?storedToken():'');$('writeToken').value='';if(!token)throw new HubError('填写此管理仓库的 GitHub 写入凭证后即可自动保存。');
    if(different&&state.dirty)throw new HubError('先同步当前修改，或导出备份后再切换仓库。');state.client.clearToken();config=next;rememberCredential(token,$('rememberToken').checked);localWrite(CONFIG,config);state.client=new GitHubClient(config.repository_url,{token});state.remoteLoaded=false;if(different){state.registry=blankRegistry();state.baseFileHash=null;state.baseRegistry=null;sync.acknowledge();}
    await readRemote();if(state.dirty){if(!sync.dirty)sync.touch();await sync.retry();}$('settingsStatus').textContent=state.dirty?(state.saving?'授权已启用，正在同步当前修改…':'修改尚未同步，请查看上方提示。'):'自动同步已启用。新增、编辑与勾选会自动保存。';await render();
  }catch(e){$('settingsStatus').textContent=e.message;notice(e.message,true);}
});
action($('clearToken'),()=>{ensureConnectionMutable();state.client.clearToken();rememberCredential('',false);$('writeToken').value='';$('rememberToken').checked=false;$('settingsStatus').textContent='已清除授权，现有 GitHub 数据仍可读取。';render();});
action($('exportLocal'),()=>download(JSON.stringify({type:'novel-hub-local-backup-v1',exported_at:new Date().toISOString(),config,registry:state.registry,chats:Object.fromEntries(state.registry.books.filter(b=>b.chat_url).map(b=>[b.id,b.chat_url])),reader_url:state.registry.settings?.reader_url||''},null,2),'续章_清单备份_'+dayInShanghai()+'.json','application/json'));
const importInput=el('input');importInput.type='file';importInput.accept='.json,application/json';importInput.hidden=true;document.body.append(importInput);action($('importLocal'),()=>importInput.click());
importInput.addEventListener('change',async()=>{try{const file=importInput.files?.[0];if(!file)return;if(file.size>4000000)throw new HubError('备份超过4MB。');const backup=validateLocalBackup(JSON.parse(await file.text()));const incoming={...backup.registry,books:backup.registry.books.map(b=>({...b,...(b.chat_url||backup.chats[b.id]?{chat_url:b.chat_url||backup.chats[b.id]}:{})}))};const merged=mergeRegistries(state.registry,incoming);if(merged.conflicts.length)throw new HubError('备份和当前清单存在同书不同设置，请先编辑核对。');state.registry=validateRegistry(merged.registry);if(!state.registry.settings?.reader_url&&backup.reader_url)state.registry.settings={reader_url:backup.reader_url};changed();toast('备份已合并到当前清单，自动同步已排队。');}catch(e){notice(e.message,true);}finally{importInput.value='';}});
action($('exportReport'),()=>{const report=state.live||state.report;if(state.checking||report?.complete===false)throw new HubError('查询完成后再导出全部结果。');if(!report)throw new HubError('先查询今天更新。');download(JSON.stringify(report,null,2),'更新查询_'+report.date+'.json','application/json');});
window.addEventListener('beforeunload',event=>{if(state.dirty){event.preventDefault();event.returnValue='';}});
let lastRefresh=0;document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!state.dirty&&!sync.running&&Date.now()-lastRefresh>60000){lastRefresh=Date.now();readRemote().catch(e=>notice('刷新失败，仍显示上次内容：'+e.message,true));}});
if(state.dirty)sync.touch();await render();try{await readRemote({initial:true});}catch(e){state.syncStatus='error';notice('GitHub 暂时未能读取，已保留本机内容：'+e.message,true);await render();}
