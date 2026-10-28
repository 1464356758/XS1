// Progress is local convenience, never evidence of publication.
export function progressKey(repository,branch,bookId,kind='reading'){
  return 'novel-hub-'+kind+'-v2:'+repository.toLowerCase()+':'+(branch||'default')+':'+(bookId||'empty');
}
export function readingChapter(chapters,progress){
  const n=progress?.chapter;
  return chapters.find(c=>Number.isInteger(n)&&c.number===n)||chapters[0]||null;
}
export function copiedChapter(chapters,progress){
  if(!chapters.length)return null;
  const n=progress?.chapter,previous=chapters.find(c=>Number.isInteger(n)&&c.number===n);
  if(!previous)return chapters[0];
  // A revised chapter must be checked again before suggesting the next one.
  if(progress.sha256&&previous.sha256!==progress.sha256)return previous;
  return chapters.find(c=>c.number===n+1)||previous;
}
export function captureChapter(book,chapter,text){
  if(!book||!chapter||typeof text!=='string')throw new Error('正文尚未核验。');
  return Object.freeze({chapter:chapter.number,title:chapter.title,sha256:chapter.sha256,text,at:new Date().toISOString()});
}
export function publicationStatus(state,chapter){
  const receipt=state?.serialization?.published?.[String(chapter.number)];
  if(!receipt)return '仓库尚未登记本章平台发布；复制不会自动登记。';
  if(receipt.text_sha256!==chapter.sha256||typeof receipt.evidence!=='string'||!receipt.evidence.trim()||Date.parse(receipt.published_at)>Date.now()||typeof receipt.published_at!=='string'||!/(?:Z|[+-]\d{2}:\d{2})$/.test(receipt.published_at)||!Number.isFinite(Date.parse(receipt.published_at)))return '本章发布记录与当前版本不符，请作者核实。';
  const date=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(receipt.published_at));
  return '仓库已登记本章发布：'+date+'（北京时间）。实际平台状态仍以发布页面为准。';
}
export class ExportJob{
  constructor(){this.active=null;}
  start(owner){if(this.active?.owner===owner)throw new Error('整本导出正在核验，请等待完成。');this.cancel();const job={owner,cancelled:false};this.active=job;return job;}
  cancel(){if(this.active)this.active.cancelled=true;this.active=null;}
  current(job){return this.active===job&&!job.cancelled;}
  finish(job){if(this.active===job)this.active=null;}
}
