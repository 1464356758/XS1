export const QUERY_STATUS={updated:'今天已更新',not_updated:'今天未更新',unknown:'读取失败',empty:'暂无正式章节'};
const day=s=>typeof s==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(s)&&Number.isFinite(Date.parse(s+'T00:00:00Z'))&&new Date(s+'T00:00:00Z').toISOString().slice(0,10)===s;
const iso=s=>typeof s==='string'&&Number.isFinite(Date.parse(s));
const sha=(s,n)=>s===null||(typeof s==='string'&&new RegExp('^[a-f0-9]{'+n+'}$').test(s));
const check=ok=>{if(!ok)throw new Error('保存的查询记录格式无效，未覆盖已有内容。');};
export function normalizeQueryHistory(value=[]){
  check(Array.isArray(value)&&value.length<=7);const dates=new Set();
  return value.map(item=>{
    check(item&&day(item.date)&&!dates.has(item.date)&&iso(item.checked_at)&&sha(item.selection_fingerprint,64)&&item.selection_fingerprint!==null&&Array.isArray(item.observations)&&item.observations.length<=100);dates.add(item.date);const ids=new Set();
    const observations=item.observations.map(o=>{
      check(o&&typeof o.id==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(o.id)&&!ids.has(o.id)&&Object.hasOwn(QUERY_STATUS,o.status));ids.add(o.id);
      check(o.book_id===null||(typeof o.book_id==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(o.book_id)));
      check(o.chapter===null||(Number.isInteger(o.chapter)&&o.chapter>=0&&o.chapter<=2000));
      check(sha(o.body_sha256,64)&&sha(o.repository_commit,40)&&sha(o.change_commit,40)&&(o.latest_change_at===null||iso(o.latest_change_at)));
      check(o.last_successful_at===undefined||o.last_successful_at===null||iso(o.last_successful_at));
      const error_code=String(o.error_code||'').slice(0,64);check(!error_code||/^[A-Za-z0-9_-]+$/.test(error_code));
      return {id:o.id,book_id:o.book_id,status:o.status,chapter:o.chapter,body_sha256:o.body_sha256,repository_commit:o.repository_commit,change_commit:o.change_commit,latest_change_at:o.latest_change_at,last_successful_at:o.last_successful_at||null,...(error_code?{error_code}:{})};
    });return {date:item.date,checked_at:item.checked_at,selection_fingerprint:item.selection_fingerprint,observations};
  }).sort((a,b)=>a.date.localeCompare(b.date));
}
export function mergeQueryHistory(remote=[],local=[]){const days=new Map();for(const item of [...normalizeQueryHistory(remote),...normalizeQueryHistory(local)]){const old=days.get(item.date);if(!old||Date.parse(item.checked_at)>=Date.parse(old.checked_at))days.set(item.date,item);}return [...days.values()].sort((a,b)=>a.date.localeCompare(b.date)).slice(-7);}
export function rememberQuery(registry,report){
  const history=normalizeQueryHistory(registry.query_history||[]),old=history.find(x=>x.date===report.date);
  const observations=report.results.map(r=>{
    const previous=old?.observations.find(o=>o.id===r.id&&o.book_id===r.book_id),known=r.status==='unknown'?previous:null;
    return {id:r.id,book_id:r.book_id,status:r.status,chapter:r.chapter??known?.chapter??null,body_sha256:r.body_sha256||known?.body_sha256||null,repository_commit:r.repository_commit||known?.repository_commit||null,change_commit:r.change_commit||known?.change_commit||null,latest_change_at:r.latest_change_at||known?.latest_change_at||null,last_successful_at:r.status==='unknown'?(previous?.last_successful_at||null):report.checked_at,...(r.error_code?{error_code:r.error_code}:{})};
  });
  return {...registry,query_history:mergeQueryHistory(history,[{date:report.date,checked_at:report.checked_at,selection_fingerprint:report.selection_fingerprint,observations}])};
}
