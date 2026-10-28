import {GitHubClient,HubError,validateRegistry,parseRepository,sha256,canonicalJSON,dayInShanghai} from './hub-core.mjs';
import {validateManifest} from './core.mjs';
import {QUERY_STATUS,normalizeQueryHistory,rememberQuery} from './query-model.mjs';
export {QUERY_STATUS,rememberQuery};
export async function selectionFingerprint(registry){return sha256(canonicalJSON(validateRegistry(registry).books.filter(b=>b.enabled).map(b=>({id:b.id,book_id:b.book_id,repository_url:b.repository_url,branch:b.branch})).sort((a,b)=>a.id.localeCompare(b.id))));}
function counts(results){return Object.fromEntries(Object.keys(QUERY_STATUS).map(k=>[k,results.filter(r=>r.status===k).length]));}
function priorObservation(registry,entry){for(const record of [...normalizeQueryHistory(registry.query_history||[])].reverse()){const o=record.observations.find(x=>x.id===entry.id&&x.book_id===entry.book_id&&x.body_sha256&&x.chapter!==null);if(o)return {...o,observed_at:o.last_successful_at||record.checked_at};}return null;}
export async function inspectTodayBook(entry,{now=new Date(),client=new GitHubClient(entry.repository_url,{preferGit:true}),previous=null}={}){
  const base={id:entry.id,book_id:entry.book_id,title:entry.title,repository_url:entry.repository_url,status:'unknown',reason:'',chapter:null,chapter_title:'',body_sha256:null,repository_commit:null,change_commit:null,latest_change_at:null,delta:null,checked_at:new Date(now).toISOString()};
  try{
    const snapshot=await client.snapshot(entry.branch),file=await client.readJSON('online/index.json',snapshot.commit),manifest=validateManifest(file.data,client.repo||parseRepository(entry.repository_url));base.repository_commit=snapshot.commit;
    if(entry.book_id&&manifest.book.id!==entry.book_id)throw new HubError('作品身份已改变，请核对这部小说的仓库。','identity_mismatch');base.book_id=manifest.book.id||entry.book_id;
    const chapter=manifest.chapters.at(-1);if(!chapter)return {...base,status:'empty',chapter:0,reason:'仓库还没有正式章节。'};
    base.chapter=chapter.number;base.chapter_title=chapter.title;base.body_sha256=chapter.sha256;
    const changed=await client.fileHistory(chapter.text_path,snapshot.commit);
    if(!Number.isFinite(Date.parse(changed.date))||Date.parse(changed.date)>new Date(now).valueOf()+60000)throw new HubError('章节提交日期无效，不能判定今天是否更新。','invalid_chapter_date');
    base.latest_change_at=changed.date;base.change_commit=changed.commit;
    base.delta=!previous?'first_seen':chapter.number>previous.chapter?'new_chapter':chapter.sha256!==previous.body_sha256?'revised':'unchanged';
    const updated=dayInShanghai(changed.date)===dayInShanghai(now);
    return {...base,status:updated?'updated':'not_updated',reason:updated?'最新章节的最近一次提交日期是今天。':'最新章节最近更新于北京时间 '+dayInShanghai(changed.date)+'。'};
  }catch(error){return {...base,status:'unknown',reason:error.message||'未能读取章节日期。',error_code:error.code||'read_failed'};}
}
export async function inspectTodayRegistry(registry,{now=new Date(),clientFactory=b=>new GitHubClient(b.repository_url,{preferGit:true}),onProgress=()=>{}}={}){
  registry=validateRegistry(registry);const selected=registry.books.filter(b=>b.enabled),results=new Array(selected.length);let cursor=0,done=0;
  async function worker(){while(cursor<selected.length){const i=cursor++,entry=selected[i];try{results[i]=await inspectTodayBook(entry,{now,client:clientFactory(entry),previous:priorObservation(registry,entry)});}catch(e){results[i]={id:entry.id,book_id:entry.book_id,title:entry.title,repository_url:entry.repository_url,status:'unknown',reason:e.message,error_code:e.code||'read_failed',chapter:null,body_sha256:null,repository_commit:null,change_commit:null,latest_change_at:null};}onProgress(++done,selected.length,results[i],results.filter(Boolean));}}
  await Promise.all(Array.from({length:Math.min(3,selected.length)},worker));
  return {schema_version:1,type:'novel-today-query-v1',date:dayInShanghai(now),checked_at:new Date(now).toISOString(),selection_fingerprint:await selectionFingerprint(registry),counts:counts(results),results};
}
export function savedQuery(registry){
  const item=normalizeQueryHistory(registry.query_history||[]).at(-1);if(!item)return null;
  const books=new Map(registry.books.map(b=>[b.id,b]));const results=item.observations.filter(o=>books.has(o.id)).map(o=>({...o,title:books.get(o.id).title,repository_url:books.get(o.id).repository_url,chapter_title:'',reason:o.status==='unknown'?'上次查询未能读到当前章节日期。':o.status==='empty'?'尚无正式章节。':o.latest_change_at?'最新章节最近更新于北京时间 '+dayInShanghai(o.latest_change_at)+'。':'尚无章节日期。'}));
  return {schema_version:1,type:'novel-today-query-v1',date:item.date,checked_at:item.checked_at,selection_fingerprint:item.selection_fingerprint,counts:counts(results),results,saved:true};
}
export async function queryState(report,registry,now=new Date()){
  if(!report)return {fresh:false,label:'尚未查询今天更新'};
  if(report.complete===false)return {fresh:false,label:'查询尚未完成'};
  if(Date.parse(report.checked_at)>new Date(now).valueOf()+60000)return {fresh:false,label:'查询时间异常，请重新查询'};
  if(report.date!==dayInShanghai(now))return {fresh:false,label:'上次查询日期 '+report.date};
  if(report.selection_fingerprint!==await selectionFingerprint(registry))return {fresh:false,label:'勾选已变化，请重新查询'};
  const ids=registry.books.filter(b=>b.enabled).map(b=>b.id).sort();if(JSON.stringify(ids)!==JSON.stringify(report.results.map(r=>r.id).sort()))return {fresh:false,label:'上次查询范围不完整'};
  return {fresh:true,label:report.saved?'今天上次保存的查询结果':'本次查询结果'};
}
