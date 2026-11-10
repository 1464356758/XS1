import {parseRepository, validateManifest, sha256, canonicalJSON, ReaderError} from './core.mjs';
import {githubFetch,parseGitRefs,parseCommitFeed} from './github-transport.mjs';
import {normalizeQueryHistory} from './query-model.mjs';
export {parseRepository, sha256, canonicalJSON};

export const HUB_VERSION='1.4.9';
export const REFERENCE_LIBRARY='https://github.com/1464356758/XS-KU';
export const SYSTEM_REPOSITORY='https://github.com/1464356758/xiaishuo-ZUOZONG';
export const TEMPLATE_REPOSITORY='https://github.com/1464356758/xiaoshuoV5';
export const STATUS={updated:'已更新',missing:'未更新',pending:'未完成',unknown:'待核实',not_due:'尚未到期',paused:'不参与检查',setup:'待初始化'};
export class HubError extends ReaderError{}
let publicApiRetryAt=0;
const fail=(condition,message,code='invalid_data')=>{if(!condition)throw new HubError(message,code);};
const hashOK=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
const commitOK=x=>typeof x==='string'&&/^[a-f0-9]{40}$/.test(x);
export function randomId(){const bytes=new Uint8Array(16);fail(globalThis.crypto?.getRandomValues,'当前浏览器不支持随机编号，请使用新版浏览器和 HTTPS。');crypto.getRandomValues(bytes);return [...bytes].map(x=>x.toString(16).padStart(2,'0')).join('');}
export function dayInShanghai(value=new Date()){
  const d=new Date(value);fail(Number.isFinite(d.valueOf()),'日期无效。');
  return new Date(d.valueOf()+8*3600000).toISOString().slice(0,10);
}
export function tomorrow(value=new Date()){return dayInShanghai(new Date(new Date(value).valueOf()+86400000));}
export function validDay(s){return typeof s==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(s)&&!Number.isNaN(Date.parse(s+'T00:00:00Z'))&&new Date(s+'T00:00:00Z').toISOString().slice(0,10)===s;}
export function safeBranch(value=''){
  const s=String(value).trim();
  fail(!s||(s.length<=200&&/^[A-Za-z0-9_][A-Za-z0-9_.\/-]*$/.test(s)&&!s.includes('..')&&!s.includes('//')&&!s.endsWith('/')&&!s.endsWith('.')&&!s.endsWith('.lock')&&!s.includes('@{')),'分支名称无效。');return s;
}
export function safePath(s){fail(typeof s==='string'&&s.length<=500&&!s.startsWith('/')&&!s.includes('\\')&&s.split('/').every(p=>p&&p!=='.'&&p!=='..')&&!/[\x00-\x1f?#]/.test(s),'文件路径无效。');return s;}
export function blankRegistry(){return {schema_version:1,type:'novel-hub-registry-v1',revision:0,timezone:'Asia/Shanghai',updated_at:null,books:[]};}
export function validateRegistry(value){
  fail(value&&value.type==='novel-hub-registry-v1'&&value.schema_version===1&&value.timezone==='Asia/Shanghai'&&Number.isInteger(value.revision)&&value.revision>=0&&Array.isArray(value.books)&&value.books.length<=100,'小说清单格式无效，未覆盖本地内容。');
  const ids=new Set(),repos=new Set(),bookIds=new Set();
  const books=value.books.map(b=>{
    fail(b&&typeof b.id==='string'&&/^[a-zA-Z0-9_-]{1,100}$/.test(b.id)&&!ids.has(b.id),'小说编号重复或无效。');ids.add(b.id);
    const repo=parseRepository(b.repository_url),branch=safeBranch(b.branch||'');
    fail(!repos.has(repo.key),'同一个仓库不能重复加入清单。');repos.add(repo.key);
    fail(typeof b.title==='string'&&b.title.trim()&&b.title.length<=300&&typeof b.enabled==='boolean','小说名称或检查开关无效。');
    fail(b.book_id===null||(typeof b.book_id==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(b.book_id)&&!bookIds.has(b.book_id)),'作品身份重复或无效，请检查是否复制了另一部书的状态。');if(b.book_id)bookIds.add(b.book_id);
    fail(/^([01]\d|2[0-3]):[0-5]\d$/.test(b.expected_time)&&Number.isInteger(b.grace_minutes)&&b.grace_minutes>=0&&b.grace_minutes<=360&&validDay(b.effective_from),'计划时间或起算日期无效。');
    let baseline=null;
    if(b.baseline){fail(Number.isInteger(b.baseline.chapter_count)&&b.baseline.chapter_count>=0&&commitOK(b.baseline.commit),'小说检查基线无效。');baseline={chapter_count:b.baseline.chapter_count,commit:b.baseline.commit,captured_at:String(b.baseline.captured_at||'')};}
    return {id:b.id,book_id:b.book_id,title:b.title.trim(),repository_url:repo.url,branch,enabled:b.enabled,expected_time:b.expected_time,grace_minutes:b.grace_minutes,effective_from:b.effective_from,baseline,...(b.chat_url?{chat_url:validateChatURL(b.chat_url)}:{}),...(b.feedback_url?{feedback_url:validateChatURL(b.feedback_url)}:{})};
  });
  return {schema_version:1,type:value.type,revision:value.revision,timezone:'Asia/Shanghai',updated_at:value.updated_at||null,books,...(value.settings?{settings:{reader_url:value.settings.reader_url?validateReaderURL(value.settings.reader_url):''}}:{}),...(value.query_history?{query_history:normalizeQueryHistory(value.query_history)}:{})};
}
export async function registryFingerprint(registry){const {query_history,...value}=validateRegistry(registry);return sha256(canonicalJSON(value));}
export function validateChatURL(value){
  if(!String(value||'').trim())return '';
  let u;try{u=new URL(String(value).trim());}catch{throw new HubError('GPT 聊天链接无效。');}
  fail(u.protocol==='https:'&&u.hostname==='chatgpt.com'&&!u.username&&!u.password&&!u.port&&/^\/(c|g|work|codex|scheduled)(\/|$)/.test(u.pathname),'仅接受 chatgpt.com 的聊天或任务链接。');return u.href;
}
export function validateReaderURL(value){
  const u=new URL(value);fail((u.protocol==='https:'||(u.protocol==='http:'&&['localhost','127.0.0.1','terminal.local'].includes(u.hostname)))&&!u.username&&!u.password&&!u.search&&!u.hash,'代发网址须为无凭证、无参数的 HTTPS 地址。');
  if(u.pathname.endsWith('/'))u.pathname+='reader.html';fail(u.pathname.endsWith('/reader.html'),'请填写以 /reader.html 结尾的代发网址。');return u.href;
}
export function validateLocalBackup(value){
  fail(value?.type==='novel-hub-local-backup-v1','不是本软件的本机备份。');
  const registry=validateRegistry(value.registry),config=value.config?.repository_url?{repository_url:parseRepository(value.config.repository_url).url,branch:safeBranch(value.config.branch||'')}:{};
  const chats={};for(const [id,url] of Object.entries(value.chats||{})){fail(/^[A-Za-z0-9_-]{1,100}$/.test(id),'备份聊天编号无效。');chats[id]=validateChatURL(url);}
  fail(Array.isArray(value.ledger||[])&&(value.ledger||[]).length<=10000,'旧备份记录过多或格式无效。');
  const ledger=[];
  return {registry,config,chats,ledger,reader_url:value.reader_url?validateReaderURL(value.reader_url):''};
}
const to64=bytes=>{let s='';for(const x of bytes)s+=String.fromCharCode(x);return btoa(s).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');};
const from64=s=>{fail(/^[A-Za-z0-9_-]+$/.test(s),'代发码格式无效。');try{return Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));}catch{throw new HubError('代发码无法解码。');}};
export async function encodeLocator({repository_url,branch='',book_id=null}){
  const repo=parseRepository(repository_url);safeBranch(branch);
  const body=JSON.stringify({v:1,r:repo.owner+'/'+repo.name,b:branch,i:book_id});
  return 'NX1.'+to64(new TextEncoder().encode(body))+'.'+(await sha256(body)).slice(0,12);
}
export async function decodeLocator(code){
  const s=String(code||'').trim();fail(s.length<=2500,'代发码过长。');const m=/^NX1\.([A-Za-z0-9_-]+)\.([a-f0-9]{12})$/.exec(s);fail(m,'代发码格式不正确，请完整复制。');
  let body,value;try{body=new TextDecoder('utf-8',{fatal:true}).decode(from64(m[1]));value=JSON.parse(body);}catch{throw new HubError('代发码内容无效。');}
  fail((await sha256(body)).slice(0,12)===m[2],'代发码校验不通过，可能复制不完整。');
  fail(value.v===1&&typeof value.r==='string','代发码版本不支持。');const repo=parseRepository(value.r),branch=safeBranch(value.b);
  fail(value.i===null||(typeof value.i==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(value.i)),'代发码作品编号无效。');
  return {repository_url:repo.url,branch,book_id:value.i};
}

async function responseText(response,maxBytes){
  fail(Number(response.headers?.get?.('content-length')||0)<=maxBytes,'文件超过读取上限。','too_large');
  let bytes;
  if(response.body?.getReader){const reader=response.body.getReader(),chunks=[];let size=0;while(true){const x=await reader.read();if(x.done)break;size+=x.value.byteLength;if(size>maxBytes){await reader.cancel();throw new HubError('文件超过读取上限。','too_large');}chunks.push(x.value);}bytes=new Uint8Array(size);let p=0;for(const c of chunks){bytes.set(c,p);p+=c.length;}}
  else {bytes=new Uint8Array(await response.arrayBuffer());fail(bytes.length<=maxBytes,'文件超过读取上限。','too_large');}
  try{return new TextDecoder('utf-8',{fatal:true}).decode(bytes).replace(/\r\n?/g,'\n');}catch{throw new HubError('文件不是有效 UTF-8。','encoding');}
}
export class GitHubClient{
  #token='';
  constructor(repository,{token='',fetcher=githubFetch,timeout=20000,preferGit=fetcher===githubFetch}={}){this.repo=parseRepository(repository);this.fetcher=fetcher;this.timeout=timeout;this.preferGit=preferGit;this.#token=String(token).trim();}
  clearToken(){this.#token='';}
  get canWrite(){return !!this.#token;}
  async request(url,{method='GET',body,maxBytes=4000000,auth=true,accept='application/vnd.github+json'}={}){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),this.timeout);
    const headers={Accept:accept};
    const isApi=url.startsWith('https://api.github.com/repos/'+encodeURIComponent(this.repo.owner)+'/'+encodeURIComponent(this.repo.name)+'/')||url===this.api('');
    const historyPrefix='https://github.com/'+encodeURIComponent(this.repo.owner)+'/'+encodeURIComponent(this.repo.name)+'/commits/';
    const isHistory=url.startsWith(historyPrefix)&&/^[a-f0-9]{40}\/book\/chapters\/CH\d{3,6}_[a-f0-9]{64}\.txt\.atom$/.test(url.slice(historyPrefix.length));
    fail(isApi||isHistory||url===this.gitURL()||url.startsWith('https://raw.githubusercontent.com/'+encodeURIComponent(this.repo.owner)+'/'+encodeURIComponent(this.repo.name)+'/'),'不允许访问其他服务。');
    if(isApi&&method==='GET'&&!(auth&&this.#token)&&Date.now()<publicApiRetryAt){clearTimeout(timer);throw new HubError('GitHub 公开接口访问额度暂时不足，请稍后重试。','rate_limit');}
    if(method!=='GET'||(auth&&this.#token))headers['X-GitHub-Api-Version']='2026-03-10';
    if(auth&&isApi&&this.#token)headers.Authorization='Bearer '+this.#token;
    if(body!==undefined)headers['Content-Type']='application/json';
    try{
      const response=await this.fetcher(url,{method,headers:isApi?headers:{},body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal,cache:'no-store',credentials:'omit',redirect:'error',referrerPolicy:'no-referrer'});
      if(isApi&&response.headers.get('x-ratelimit-remaining')==='0'){const reset=Number(response.headers.get('x-ratelimit-reset'))*1000;if(Number.isFinite(reset)&&reset>Date.now())publicApiRetryAt=Math.min(reset,Date.now()+3600000);}
      if(!response.ok){const status=response.status,relay=response.headers.get('x-novel-error');if(status===404)throw new HubError('文件或仓库不存在，请确认仓库公开、路径和分支正确。','not_found');if(status===409||status===422)throw new HubError('远端版本有变化，先重新读取后再保存。','conflict');if(status===401){if(method==='GET'&&auth&&this.#token){response.body?.cancel();return await this.request(url,{method,body,maxBytes,auth:false,accept});}throw new HubError('GitHub 凭证无效或已过期，请重新授权自动保存。','auth');}if(status===403||status===429)throw new HubError('GitHub 权限不足或访问受限，请检查授权及限流情况。','rate_limit');if(status===413)throw new HubError('文件超过读取上限。','too_large');if(relay==='upstream_timeout')throw new HubError('网站连接 GitHub 超时，请稍后重试。','timeout');if(relay==='upstream_network')throw new HubError('网站暂时无法连接 GitHub，请稍后重试。','network');throw new HubError('GitHub 访问失败（'+status+'）。','network');}
      return await responseText(response,maxBytes);
    }catch(error){if(error instanceof HubError)throw error;if(error.name==='AbortError')throw new HubError('读取仓库超时，请稍后重新核验。','timeout');throw new HubError('仓库连接失败：当前站点的 GitHub 读取通道不可用，请稍后重试。','network');}
    finally{clearTimeout(timer);}
  }
  api(path){return 'https://api.github.com/repos/'+encodeURIComponent(this.repo.owner)+'/'+encodeURIComponent(this.repo.name)+(path?'/'+path:'');}
  async json(path,options={}){const text=await this.request(this.api(path),options);try{return JSON.parse(text);}catch{throw new HubError('GitHub 返回了无法解析的数据。');}}
  gitURL(){return 'https://github.com/'+encodeURIComponent(this.repo.owner)+'/'+encodeURIComponent(this.repo.name)+'.git/info/refs?service=git-upload-pack';}
  async gitRefs(){let refs;try{refs=parseGitRefs(await this.request(this.gitURL(),{auth:false}));}catch(e){if(e instanceof HubError)throw e;throw new HubError('无法解析公开仓库的提交版本，请稍后重试。','invalid_git_refs');}return refs;}
  async publicInfo(){
    if(this.preferGit){const git=await this.gitRefs();fail(git.defaultBranch,'无法识别公开仓库默认分支。');return {private:false,full_name:this.repo.owner+'/'+this.repo.name,default_branch:git.defaultBranch};}
    let info;try{info=await this.json('');}catch(e){if(!['network','timeout','rate_limit'].includes(e.code))throw e;const git=await this.gitRefs();fail(git.defaultBranch,'无法识别公开仓库默认分支。');info={private:false,full_name:this.repo.owner+'/'+this.repo.name,default_branch:git.defaultBranch};}
    fail(info.private===false,'当前版本仅支持公开仓库。','private_repo');return info;
  }
  async snapshot(branch=''){
    if(this.preferGit){safeBranch(branch);const git=await this.gitRefs(),commit=git.refs[branch&&branch!=='HEAD'?'refs/heads/'+branch:'HEAD'];fail(commit,'公开仓库不存在这个分支。','not_found');return {commit,branch:branch&&branch!=='HEAD'?branch:git.defaultBranch||'',committed_at:null};}
    safeBranch(branch);let value,resolvedBranch=branch&&branch!=='HEAD'?branch:'';try{value=await this.json('commits/'+encodeURIComponent(branch||'HEAD'));}catch(e){
      if(!['network','timeout','rate_limit'].includes(e.code))throw e;
      const git=await this.gitRefs(),commit=git.refs[branch&&branch!=='HEAD'?'refs/heads/'+branch:'HEAD'];
      fail(commit,'公开仓库不存在这个分支。','not_found');value={sha:commit};resolvedBranch||=git.defaultBranch||'';
    }
    fail(commitOK(value.sha),'无法确认仓库提交版本。');
    return {commit:value.sha,branch:resolvedBranch,committed_at:value.commit?.committer?.date||null};
  }
  async readFile(path,commit){
    safePath(path);fail(commitOK(commit),'必须先确定仓库提交版本。');
    const url='https://raw.githubusercontent.com/'+encodeURIComponent(this.repo.owner)+'/'+encodeURIComponent(this.repo.name)+'/'+commit+'/'+path.split('/').map(encodeURIComponent).join('/');
    let text;try{text=await this.request(url,{auth:false});}catch(error){
      if(this.preferGit)throw error;
      if(!['network','timeout','rate_limit','not_found'].includes(error.code))throw error;
      // Both sources are pinned to the same commit; never mix HEAD files into
      // a verified snapshot. The Contents raw media type also supports >1MB.
      try{text=await this.request(this.api('contents/'+path.split('/').map(encodeURIComponent).join('/')+'?ref='+commit),{auth:false,accept:'application/vnd.github.raw+json'});}catch(alternate){
        // A real 404 from the primary immutable URL is evidence of absence.
        // An unavailable alternate must not replace it with a quota error.
        if(error.code==='not_found'&&['rate_limit','network','timeout'].includes(alternate.code))throw error;
        if(['network','timeout','rate_limit'].includes(error.code)&&alternate.code==='rate_limit')throw new HubError('文件读取暂时不可用，主要读取和备用读取都未成功，请稍后重试。','network');
        throw alternate;
      }
    }return {text,hash:await sha256(text)};
  }
  async readJSON(path,commit){const file=await this.readFile(path,commit);try{return {...file,data:JSON.parse(file.text.replace(/^\uFEFF/,''))};}catch{throw new HubError(path+' 的 JSON 格式无效。');}}
  async optionalJSON(path,commit){try{return await this.readJSON(path,commit);}catch(e){if(e.code==='not_found')return null;throw e;}}
  async fileHistory(path,commit){
    safePath(path);fail(commitOK(commit)&&/^book\/chapters\/CH\d{3,6}_[a-f0-9]{64}\.txt$/.test(path),'只能查询正式章节文件的提交日期。');
    const url='https://github.com/'+encodeURIComponent(this.repo.owner)+'/'+encodeURIComponent(this.repo.name)+'/commits/'+commit+'/'+path+'.atom';
    const raw=await this.request(url,{auth:false});let history;try{history=parseCommitFeed(raw);}catch(e){throw new HubError(e.message,'invalid_history');}
    const source=/^tag:github\.com,2008:\/([^/]+)\/([^/]+)\/commits\/([a-f0-9]{40})\/(.+)$/.exec(history.sourceId||'');
    fail(source&&source[1].toLowerCase()===this.repo.owner.toLowerCase()&&source[2].toLowerCase()===this.repo.name.toLowerCase()&&source[3]===commit&&source[4]===path,'章节日期来源与查询文件不一致。','invalid_history');return history;
  }
  async putFile(path,content,{branch,expectedHead}={}){
    fail(this.canWrite,'请先授权 GitHub 自动同步。','auth');safePath(path);fail(safeBranch(branch)&&commitOK(expectedHead),'保存分支或版本无效。');
    let previous;try{previous=await this.json('contents/'+path.split('/').map(encodeURIComponent).join('/')+'?ref='+expectedHead);}catch(e){if(e.code!=='not_found')throw e;}
    if(previous)fail(previous.type==='file'&&commitOK(previous.sha),'远端文件版本无效。');
    const bytes=new TextEncoder().encode(content);let encoded='';for(const byte of bytes)encoded+=String.fromCharCode(byte);
    const result=await this.json('contents/'+path.split('/').map(encodeURIComponent).join('/'),{method:'PUT',body:{message:'Save novel workspace',branch,content:btoa(encoded),...(previous?{sha:previous.sha}:{})}});
    fail(commitOK(result.commit?.sha),'GitHub 未返回已保存版本。','uncertain_write');
    const file=await this.readFile(path,result.commit.sha);fail(file.text===content,'保存后的文件尚未核对成功，请重试同步。','uncertain_write');
    return {commit:result.commit.sha,observed_commit:result.commit.sha};
  }
  async writeFiles(files,{expectedHead,branch}={}){
    fail(this.canWrite,'请先在设置中临时填写 GitHub 写入凭证。','auth');fail(commitOK(expectedHead)&&safeBranch(branch),'写入前必须确认分支及版本。');
    const current=await this.snapshot(branch);fail(current.commit===expectedHead,'保存前远端已变化，请重新读取。','conflict');
    const commit=await this.json('git/commits/'+expectedHead);fail(commitOK(commit.tree?.sha),'无法读取基础目录树。');
    const tree=[];for(const [path,content] of Object.entries(files)){safePath(path);fail(typeof content==='string','写入内容无效。');const b=await this.json('git/blobs',{method:'POST',body:{content,encoding:'utf-8'}});fail(commitOK(b.sha),'文件上传未返回有效版本。');tree.push({path,mode:'100644',type:'blob',sha:b.sha});}
    const t=await this.json('git/trees',{method:'POST',body:{base_tree:commit.tree.sha,tree}});
    const c=await this.json('git/commits',{method:'POST',body:{message:'Update novel workspace data',tree:t.sha,parents:[expectedHead]}});fail(commitOK(c.sha),'提交未返回有效版本。');
    await this.json('git/refs/heads/'+branch.split('/').map(encodeURIComponent).join('/'),{method:'PATCH',body:{sha:c.sha,force:false}});
    const observed=await this.snapshot(branch);for(const [path,content] of Object.entries(files)){const file=await this.readFile(path,observed.commit);fail(file.text===content,'写入后内容未核对成功，请重新读取。','uncertain_write');}
    return {commit:c.sha,observed_commit:observed.commit};
  }
}

export async function loadRegistry(client,branch=''){
  const info=await client.publicInfo(),actualBranch=branch||safeBranch(info.default_branch),snapshot=await client.snapshot(actualBranch);
  const file=await client.optionalJSON('books.json',snapshot.commit);
  return {registry:file?validateRegistry(file.data):blankRegistry(),fileHash:file?.hash||null,branch:actualBranch,head:snapshot.commit,missing:!file};
}
export async function saveRegistry(client,draft,{branch,baseFileHash}={}){
  const previous=await loadRegistry(client,branch);fail(previous.fileHash===(baseFileHash??null),'小说清单已被其他操作修改，请先重新读取；本地修改仍然保留。','conflict');
  const desired=validateRegistry(draft);
  if(!previous.missing&&canonicalJSON({books:desired.books,settings:desired.settings||{},query_history:desired.query_history||[]})===canonicalJSON({books:previous.registry.books,settings:previous.registry.settings||{},query_history:previous.registry.query_history||[]}))return {...previous,commit:previous.head,observed_commit:previous.head};
  const registry=validateRegistry({...draft,revision:previous.registry.revision+1,updated_at:new Date().toISOString()});
  const text=JSON.stringify(registry,null,2)+'\n';
  const result=await client.putFile('books.json',text,{branch:previous.branch,expectedHead:previous.head});
  return {...result,registry,fileHash:await sha256(text),branch:previous.branch};
}
export function validateReport(report){
  fail(report?.type==='novel-hub-report-v1'&&report.schema_version===1&&validDay(report.date)&&Number.isFinite(Date.parse(report.checked_at))&&hashOK(report.registry_fingerprint)&&Number.isInteger(report.registry_revision)&&Array.isArray(report.results)&&report.results.length<=100,'检查报告格式无效。');
  const ids=new Set();for(const r of report.results){fail(typeof r.id==='string'&&!ids.has(r.id)&&Object.hasOwn(STATUS,r.status)&&typeof r.reason==='string'&&typeof r.title==='string','检查报告中的小说结果无效。');ids.add(r.id);}
  for(const key of Object.keys(STATUS))fail(report.counts?.[key]===report.results.filter(r=>r.status===key).length,'报告统计与逐书结果不一致。');
  return report;
}
export async function reportState(report,registry,now=new Date()){
  if(!report)return {fresh:false,label:'今日报告未生成'};
  try{validateReport(report);}catch{return {fresh:false,label:'报告格式无效，请重新检查'};}
  if(report.date!==dayInShanghai(now))return {fresh:false,label:'今日报告未生成 · 上次 '+report.date};
  if(Date.parse(report.checked_at)>new Date(now).valueOf()+60000)return {fresh:false,label:'报告检查时间异常'};
  if(report.registry_fingerprint!==await registryFingerprint(registry))return {fresh:false,label:'清单已变更 · 此报告基于旧清单'};
  const ids=new Set(registry.books.map(b=>b.id));if(report.results.length!==ids.size||report.results.some(r=>!ids.has(r.id)))return {fresh:false,label:'报告检查范围不完整'};
  return {fresh:true,label:'今日报告已生成'};
}
export async function prefixFingerprint(state,count){
  const values=[];for(let n=1;n<=count;n++){const c=state.chapters[String(n)];fail(c&&hashOK(c.text_sha256)&&hashOK(c.record_sha256),'历史正式章节的版本不完整。');values.push({chapter:n,text_sha256:c.text_sha256,record_sha256:c.record_sha256});}
  return sha256(canonicalJSON(values));
}
export async function loadBook(client,branch=''){
  const snapshot=await client.snapshot(branch),file=await client.readJSON('online/index.json',snapshot.commit);
  const manifest=validateManifest(file.data,client.repo);
  if(manifest.initialized===false)return {snapshot,manifest,state:null};
  const raw=await client.readJSON('book/state.json',snapshot.commit);
  fail(raw.hash===manifest.source.state_sha256,'阅读索引落后于正式状态，请让 GPT 重建索引。','stale_index');
  const state=raw.data;fail(state.book_id===manifest.book.id&&Object.keys(state.chapters||{}).length===manifest.chapters.length,'作品身份或章节数量不一致。');
  for(const c of manifest.chapters){const item=state.chapters[String(c.number)];fail(item&&item.text_sha256===c.sha256&&'book/'+item.text_path===c.text_path,'章节目录与正式状态不一致。');}
  if(state.config?.serial_mode===true||state.serialization!==undefined){
    const serial=state.serialization;
    fail(serial?.enabled===true&&Object.keys(serial.frozen||{}).length===manifest.chapters.length,'正式章节的冻结状态不完整，请先核对仓库。','invalid_frozen');
    for(const c of manifest.chapters){const item=state.chapters[String(c.number)],pin=serial.frozen[String(c.number)];fail(pin&&hashOK(item.record_sha256)&&pin.text_sha256===item.text_sha256&&pin.record_sha256===item.record_sha256,'正式章节与冻结版本不一致，已停止复制和导出。','invalid_frozen');}
  }
  return {snapshot,manifest,state};
}
export async function readFormalChapter(client,book,chapter){
  fail(chapter&&!chapter.storage&&!chapter.needs_revalidation,'本章需要重新核对或仍使用旧加密格式。');
  const file=await client.readFile(chapter.text_path,book.snapshot.commit);fail(file.hash===chapter.sha256,'正文与正式目录校验不一致，已停止复制和导出。','hash_mismatch');return file.text;
}
export function suggestedChapter(chapters,progress){if(!chapters.length)return null;const n=Number(progress?.chapter),previous=chapters.find(c=>c.number===n);if(!Number.isInteger(n)||n<1||!previous)return chapters[0];if(progress.sha256&&previous.sha256!==progress.sha256)return previous;return chapters.find(c=>c.number===n+1)||previous;}
function proof(condition,message){fail(condition,message,'invalid_receipt');}
export async function verifyCompletion(client,book,receipt,date,now=new Date()){
  const {state,manifest,snapshot}=book,r=receipt;
  proof(r?.type==='novel-daily-completion-v1'&&r.schema_version===1&&r.status==='completed'&&r.date===date&&r.book_id===state.book_id,'完成记录的日期或作品身份不匹配。');
  proof(typeof r.run_id==='string'&&/^[A-Za-z0-9_-]{8,100}$/.test(r.run_id)&&typeof r.work_id==='string'&&validDay(r.start_date),'完成记录缺少执行编号。');
  proof(Number.isInteger(r.chapter)&&r.chapter>0&&Number.isInteger(r.baseline_count)&&r.chapter===r.baseline_count+1,'完成记录的目标章无效。');
  proof(r.work_id===r.book_id+':'+r.start_date+':'+r.chapter,'完成记录的任务编号不匹配。');
  const ended=Date.parse(r.completed_at),started=Date.parse(r.started_at);
  proof(Number.isFinite(ended)&&Number.isFinite(started)&&ended>=started&&ended<=new Date(now).valueOf()+60000&&dayInShanghai(ended)===date&&dayInShanghai(started)===r.start_date,'完成时间无效或并非本日更新。');
  proof(!snapshot.committed_at||ended<=Date.parse(snapshot.committed_at)+60000,'完成记录晚于所在提交，时间证据无效。');
  proof(state.serialization?.enabled===true&&!state.needs_revalidation?.includes(r.chapter),'章节尚未通过冻结采用。');
  const item=state.chapters[String(r.chapter)],pin=state.serialization.frozen?.[String(r.chapter)],gate=state.serialization.gates?.[String(r.chapter)];
  proof(item&&pin&&gate?.used===true&&item.adopted_at===r.completed_at&&item.text_sha256===r.body_sha256&&item.record_sha256===r.record_sha256&&pin.text_sha256===r.body_sha256&&pin.record_sha256===r.record_sha256,'正文、记录、采用日期或冻结依据不匹配。');
  proof(r.body_path===item.text_path&&r.record_path===item.record_path&&r.release_path===gate.path&&r.release_sha256===gate.sha256,'完成记录引用了不同的检查版本。');
  proof(await prefixFingerprint(state,r.baseline_count)===r.baseline_fingerprint,'此前正式章节被改变，无法确认连续更新。');
  const ch=manifest.chapters[r.chapter-1];proof(ch?.sha256===r.body_sha256,'目录缺少所登记的正式章节。');
  const body=await readFormalChapter(client,book,ch);
  const rec=await client.readJSON('book/'+safePath(r.record_path),snapshot.commit),release=await client.readJSON('book/'+safePath(r.release_path),snapshot.commit);
  proof(rec.hash===r.record_sha256&&release.hash===r.release_sha256,'章后记录或检查报告校验失败。');
  proof(rec.data.chapter===r.chapter&&rec.data.text_sha256===r.body_sha256&&release.data.chapter===r.chapter&&release.data.book_id===r.book_id&&release.data.text_sha256===r.body_sha256&&release.data.record_sha256===r.record_sha256&&release.data.decision==='release'&&release.data.read_full_text===true&&Array.isArray(release.data.blocking_issues)&&release.data.blocking_issues.length===0,'检查报告未通过或对应另一份正文。');
  proof(body.trim().length>0,'正文为空。');return {chapter:r.chapter,sha256:r.body_sha256,completed_at:r.completed_at,run_id:r.run_id,release_sha256:r.release_sha256};
}
export async function inspectExecution(entry,{now=new Date(),client=new GitHubClient(entry.repository_url)}={}){
  const result={book_id:entry.book_id,status:'unknown',label:'尚未核实',reason:'',commit:null,chapter:null,checked_at:new Date(now).toISOString()};
  try{
    const book=await loadBook(client,entry.branch);result.commit=book.snapshot.commit;
    fail(!entry.book_id||entry.book_id===book.manifest.book.id,'作品身份已改变，请核对仓库。','identity_mismatch');
    result.book_id=book.manifest.book.id;
    if(!book.state)return {...result,status:'setup',label:'尚未初始化',reason:'先完成本书平台、选题和规划。'};
    const day=dayInShanghai(now),receipt=await client.optionalJSON('book/daily/'+day+'.json',result.commit);
    if(receipt){const evidence=await verifyCompletion(client,book,receipt.data,day,now);return {...result,status:'completed',label:'本日正式章已核验',chapter:evidence.chapter,evidence,reason:'已核对正文、冻结、审查和完成回执；平台发布另行确认。'};}
    const file=await client.optionalJSON('book/daily/active.json',result.commit),active=file?.data;
    if(active){
      fail(active.type==='novel-daily-task-v1'&&active.book_id===result.book_id&&['running','blocked','completed'].includes(active.status)&&Number.isInteger(active.chapter)&&active.chapter>0&&/^[A-Za-z0-9_-]{8,100}$/.test(active.run_id||''),'执行记录身份或状态无效。','invalid_active');
      result.chapter=active.chapter;
      if(active.status==='running')return {...result,status:'pending',label:'有未完成执行记录',reason:'目标第'+active.chapter+'章。仓库记录不能证明任务仍存活；先核实原执行，再恢复同一目标。'};
      if(active.status==='blocked'){
        const recovery=active.operator_recovery;
        if(recovery?.status==='ready'){
          fail(recovery.ready_run_id===active.run_id&&recovery.expected_state_sha256===book.manifest.source.state_sha256&&active.chapter===book.manifest.chapters.length+1&&hashOK(recovery.grant_sha256)&&hashOK(recovery.audit_sha256)&&typeof recovery.old_run_id==='string'&&recovery.old_run_id!==active.run_id,'维护恢复检查点与当前作品或目标不一致。','invalid_recovery');
          return {...result,status:'recovery_ready',label:'维护恢复检查点已准备',reason:'等待本书既有任务按 preflight → begin 核验授权与归档，再接续第'+active.chapter+'章；当前记录不代表章节已完成。'};
        }
        return {...result,status:'blocked',label:'执行已记录中断',reason:active.reason||'核实原执行停止后，继续原目标章。'};
      }
      const completedDay=dayInShanghai(active.completed_at),old=completedDay===day?null:await client.optionalJSON('book/daily/'+completedDay+'.json',result.commit);
      if(!old)throw new HubError('执行标为完成但对应回执缺失，请先恢复原目标的完成证据，不能直接开下一章。','missing_receipt');
      const evidence=await verifyCompletion(client,book,old.data,completedDay,now);fail(evidence.run_id===active.run_id&&evidence.chapter===active.chapter,'执行记录与完成回执不匹配。','invalid_active');
    }
    if(!book.state.serialization?.enabled)return {...result,status:'legacy',label:'旧书需核对接入条件',reason:'缺少可核验的连载冻结机制；不自动追认旧章。'};
    return {...result,status:'waiting',label:'暂无本日完成回执',reason:'未发现本日正式完成证据；这不代表定时任务已建立或未建立。'};
  }catch(error){return {...result,status:'unknown',label:'读取或核验未通过',reason:error.message,error_code:error.code||'read_failed'};}
}
export async function inspectBook(entry,{now=new Date(),client=new GitHubClient(entry.repository_url)}={}){
  const date=dayInShanghai(now),base={id:entry.id,book_id:entry.book_id,title:entry.title,checked_at:new Date(now).toISOString(),status:'unknown',reason:'',chapters:null,commit:null};
  if(!entry.enabled)return {...base,status:'paused',reason:'当前清单未勾选。'};
  if(entry.effective_from>date)return {...base,status:'not_due',reason:'从 '+entry.effective_from+' 起参与检查。'};
  try{
    const book=await loadBook(client,entry.branch);base.commit=book.snapshot.commit;base.chapters=book.manifest.chapters.length;base.book_id=book.manifest.book.id;
    fail(!entry.book_id||entry.book_id===base.book_id,'当前仓库的作品身份已改变。','identity_mismatch');
    if(!book.state)return {...base,status:'setup',reason:'小说尚未初始化，请先完成平台、选题和规划。'};
    const receipt=await client.optionalJSON('book/daily/'+date+'.json',base.commit);
    if(receipt){const evidence=await verifyCompletion(client,book,receipt.data,date,now);return {...base,status:'updated',reason:'已核对本日正文、冻结记录和检查报告。',evidence,unreported_chapters:book.manifest.chapters.filter(c=>c.publication_status!=='confirmed').length};}
    const due=Date.parse(date+'T'+entry.expected_time+':00+08:00')+entry.grace_minutes*60000;
    const active=await client.optionalJSON('book/daily/active.json',base.commit);
    if(active){fail(active.data.book_id===base.book_id,'执行记录属于另一部小说。');if(['running','blocked'].includes(active.data.status))return {...base,status:'pending',reason:active.data.reason||('目标第'+active.data.chapter+'章，'+(active.data.status==='running'?'执行状态尚待确认。':'执行未完成，需恢复原目标。'))};}
    if(new Date(now).valueOf()<due)return {...base,status:'not_due',reason:'计划 '+entry.expected_time+'，另有 '+entry.grace_minutes+' 分钟完成宽限。'};
    if(!book.state.serialization?.enabled)return {...base,status:'unknown',reason:'旧书尚未启用可核验的冻结记录，不能凭字数判断今日完成。'};
    return {...base,status:'missing',reason:'未发现今日有效完成记录；新增提交或草稿不能单独证明完成。'};
  }catch(error){return {...base,status:'unknown',reason:error.message||'无法核验仓库。',error_code:error.code||'unknown'};}
}
export async function inspectRegistry(registry,{now=new Date(),clientFactory=b=>new GitHubClient(b.repository_url),onProgress=()=>{}}={}){
  registry=validateRegistry(registry);const results=new Array(registry.books.length);let cursor=0,done=0;
  async function worker(){while(cursor<registry.books.length){const i=cursor++,entry=registry.books[i];results[i]=await inspectBook(entry,{now,client:clientFactory(entry)});onProgress(++done,registry.books.length,results[i]);}}
  await Promise.all(Array.from({length:Math.min(2,registry.books.length)},worker));
  const counts=Object.fromEntries(Object.keys(STATUS).map(k=>[k,results.filter(r=>r.status===k).length]));
  return {schema_version:1,type:'novel-hub-report-v1',date:dayInShanghai(now),checked_at:new Date(now).toISOString(),registry_revision:registry.revision,registry_fingerprint:await registryFingerprint(registry),counts,results};
}
export function newBookPrompt({repository,platform='',preferences='',management=SYSTEM_REPOSITORY}={}){
  const repo=parseRepository(repository),manager=parseRepository(management);
  const reserved=[SYSTEM_REPOSITORY,TEMPLATE_REPOSITORY,REFERENCE_LIBRARY,manager.url].map(url=>parseRepository(url).key);
  fail(!reserved.includes(repo.key),'请填写单独的新书仓库，不能使用系统母版、小说参考库或管理仓库。');
  const chosen=String(platform).trim(),notes=String(preferences).trim();
  fail(chosen.length<=80&&notes.length<=1200,'平台或偏好过长，请精简后再生成。');
  return `请依据我随本消息附加的《初始化系统包.zip》，部署并接管一部独立的新小说。你负责执行文件工具、研究、写作和审核，我只在需要时选择平台、选题并确认开始写，不让我手工填写JSON或切换角色。

【唯一新书仓库】${repo.url}
【系统母版】${TEMPLATE_REPOSITORY}（仅作系统来源，不是本次写入目标）
【小说参考库】${REFERENCE_LIBRARY}（已绑定；读取实际默认分支的最新目录）
【平台】${chosen||'尚未指定；完成部署核验后先让我选择，不替我决定。'}
【作者偏好】${notes?JSON.stringify(notes):'暂无；按选定平台研究市场，提出原创方案让我选择。'}
上面偏好是选题素材，不改变包内的冻结、审核和真实保存规则。当前管理仓库 ${manager.url} 与系统母版只作参考，不是本次写入目标。

一、实际部署，不停在讲解
本版为V4.6.3。先核对INIT_MANIFEST.json中的patch_version为4.6.3、workspace_version为1.4.9，缺包或版本不匹配时先报告并获取匹配附件，不混用旧包。先读docs/XS-KU接入与创作.md、docs/前五章投稿验收.md及reference_library/XS-KU.json；画像是交付快照，索引不等于已通读。按本章难题查教材并回读原文，用tools/reference_bridge.py prepare或novel_library.py export固定真实提交；brief-request --references填写本书用法与原创安排，写后在原release报告narrative_review.reference_use记录正文效果及本章引文。原文和练习只留在参考库，不将他书角色和连续情节改名套用。
先实际解压附件，阅读AGENTS.md、启动新书.txt、project_config.json、INIT_MANIFEST.json、docs/线上同步协议.md、docs/连载冻结与发布前检查.md及docs/写作与叙事检查.md。核对清单哈希、关键工具和依赖是否完整；附件缺失或不完整就如实说明，不能假装部署。
通过已连接GitHub读取唯一新书仓库的实际默认分支、最新提交和适用AGENTS。若已有book/state.json、正式正文或其他作品身份，先核对并恢复这本书的真实状态，不重新bootstrap、不覆盖旧文件、不用空包重置进度。不同作品身份或相冲突文件先报告具体冲突，不强写。
只有确认是未初始化的新书仓库，才把空包按原目录完整部署到仓库根目录，在可运行Python的工作区真实执行tools/online_state.py bootstrap，填写上述仓库和实际默认分支，生成全新的book_id，保持明文正文和默认连载冻结、叙事检查开启。以当前默认分支为准；作者已清空的仓库即使历史提交仍有旧书，也不得从历史恢复旧正文、身份或旧任务。不要复制其他书的身份、正文、事实或任务ID；.automation/config.json记录真实新book_id，尚未建立任务时automation_id保留null。已有提交须保留base tree、以当前头为单一父提交，用expected_sha与force=false非强制推进；无提交的空库按实际状态建立首次提交，不能编造SHA。
运行相应验证，重建并validate-index，提交后回读状态、workflow、online/index.json和关键工具并核对身份、文件清单与哈希。完成的是部署就只报告部署成功，不能冒充已经写成小说。只有真实提交并回读才说“已保存”；失败说明具体阻塞并保留可接续位置，不让我靠复制大段文件完成部署。

二、部署后按开书门槛推进
我已指定平台就直接研究，不重复问；未指定则先让我选平台，不自行选择。按平台研究与选题.md核查现行官方创作、投稿、原创与AI辅助规则、签约和可核实福利，注明核查日期与官方来源。研究公开近期榜单，区分榜单类型；访问受限就记录缺口，不捏造规则、名次、样本或收益。
默认提出8个原创选题，给暂定书名、核心卖点、主角矛盾、读者承诺、长篇展开动力、阶段变化、结局方向及主要风险。新版初始包每题补前三章结果和同题材差异。把研究和候选真实保存并同步索引，停在WAITING_TOPIC等我选择，不替我定题、不提前写正文。已有真实选择时不重复倒退。
我选定后建立设定、人物知情与资源事实账、完整长期路线和近期3—5章安排，检查长篇是否有足够变化。默认150章、约90万汉字；每章目标6000汉字、允许5500—6500，首章起统一执行。有docs/开篇试写与剧情验收.md时按其规则选题；收到我的「开始写」后再试写首章。每次只完成一个目标章。首章前整体设计五章，按docs/前五章投稿验收.md精读两部独立开篇各至少一万汉字，绑定教材范围；每章累计全文审读，第3和第5章做样稿复核，内部准备完成不能冒称签约。

三、后续持续写作的硬要求
按本书现行规则完成写前任务书、场景预算、全书历史检索，实读需要的旧章，写完整正文后做反向提纲、限信息审读、带引文的事实与因果审核及反重复检查；每五章与跨阶段的全文回看在采用前完成。同一任务最多3轮局部修订，不重置计数、不批填pass；同一上下文审读如实标same_context_approximation，不冒充独立读者。
采用前release-check，采用即冻结正文和事实记录；以后每日更新、每日发布，前面全部采用章只读，旧错只前向处理，禁止为续写修改前章。章节完成、GitHub保存、小说平台发布分别记录；不自动投稿、签约或购买额度，不承诺文学质量、签约收益或长期无人值守。
定时任务仅在我明确要求并指定时间后创建或更新：先查同书已有任务并唯一复用，将本次配置步骤与长期执行指令分开，只保存长期规则和真实仓库/book_id绑定，不把当前章次、临时草稿或旧锁写成永久状态。按docs/定时执行器.md绑定真实任务ID，先提交不写章的preflight，再核对该source_sha对应作业和result；预检通过只证明工具链可用，完整日更另须实测。每轮以最新state和begin的真实目标为准，分场景完成整章；上下文准备成功或半篇草稿不作为主动结束理由。中断保留同章检查点，核实旧控制者平台终态及执行器作业终态后合法接续，不超时抢占、不自行停用计划或另建补跑任务。普通聊天补更优先用原任务的立即运行入口，未提供时如实报告，不伪装automation controller。固定GitHub Actions只执行文件工具；不能声称脚本会再次唤醒GPT。只有chapter_completed且正式正文、审核、冻结、回执和远端哈希核验齐全才报告章节完成。模型/思考档位无真实运行元数据时标未验证，不承诺返回创建聊天。
个人端加入小说是部署完成后的独立操作；先给我可用的新书仓库链接和真实book_id，不擅自改管理清单。日常“今日更新”仍按最新正式章节文件最近提交的北京时间日期判断，不加日报或完成回执门槛。

现在先核验附件和上述仓库，实际完成部署与回读；随后按我的平台选择推进到当前合法阶段。反馈用简洁中文，给真实提交SHA、核验结果、当前阶段和我下一步只需做的选择。`;
}
function taskLocator(entry){
  const repo=parseRepository(entry.repository_url),branch=safeBranch(entry.branch||''),title=String(entry.title||'本书').trim();
  fail(title&&title.length<=300,'小说名称无效。');
  fail(entry.book_id==null||(typeof entry.book_id==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(entry.book_id)),'作品身份无效。');
  return `【小说】${JSON.stringify(title)}\n【唯一仓库】${repo.url}\n【目标分支】${branch||'每轮读取仓库实际默认分支'}\n【作品身份】${entry.book_id||'首次配置时从该仓库state核实book_id并绑定；未核实不得开始写作。'}`;
}

const DAILY_EXECUTION_RULES=`一、每轮读取真实状态
读取AGENTS.md、docs/每日自动更新.md、docs/定时执行器.md、docs/连载冻结与发布前检查.md、docs/写作与叙事检查.md、book/state.json、book/workflow.json、online/index.json、.automation/config.json及book/daily/active.json、相关回执和请求结果。核实仓库、分支HEAD、book_id与本书唯一任务ID；发现身份冲突就报告。章次、冻结、旧锁及草稿状态以远端为准，不采用任务创建时的聊天摘要。active、回执或进度文件尚不存在时，区分首次运行无记录与真实读取失败，不编造旧执行。已有作者授权按已确认路线持续日更，无需每天重问“开始”；未选题或缺少设定路线时仍不能越过开书门槛。

二、先提交，再核验执行
使用已有.github/workflows/novel-executor.yml与tools/task_executor.py，不把本地无法git clone当作唯一执行出口。每批读最新HEAD及其commit.tree.sha，把真实tree SHA传给create_tree的base_tree_sha，增量加入.automation/request.json和必要drafts；保留base tree、单一父提交、expected_sha和force=false。不必把全部递归树条目重新列出；请求提交不直接改state、冻结正文或系统源码。
每轮先提交preflight请求，再查该source_sha对应的GitHub Actions及.automation/results/<request_id>.json；没有提交前的“本轮作业”不能成为提交前提。检查request_id、source_sha、book_id、controller和完整输出。结果未知先回读远端已有请求与作业，不换编号重放操作。只有真实工具报错才记录具体工具、错误码或返回信息，不用“尚未取得”代替实际尝试。

三、取得同一目标的合法执行权
私下peek本任务，controller使用实际automation_id、每轮独立session_id和能核实的本轮platform_run_id（取不到填null并标未验证），本轮各批复用。preflight通过后由begin真正运行daily_update.py begin；回读锁与result后才写作，目标只取begin实际返回的一章。遵守本书completion_policy；per_trigger按现行协议提供同次触发重试保持一致的稳定trigger_id，不擅自改策略。already_completed停止；recovered_completion只恢复回执不续写；continue_owned沿用本轮。
先区分维护检查点和普通旧锁：若active.operator_recovery.status为ready，按既有任务preflight→begin核验已有维护授权与归档；只有begin返回resumed及recovery_mode=operator_revocation才以本轮新run_id续写原章，不补造未知的旧平台编号。其余recovery_required或另一轮blocked/running，必须先核实原controller的确切平台运行终态和全部关联执行器作业终态，才能按stopped_evidence恢复同一目标；当前新运行的终态不能冒充旧运行。无归属或无法核实的普通旧锁保留待核，不超时抢占，不伪造session或执行编号。不自行recover或制作维护授权，不删除锁、候选或返修次数。

四、完成正文和实质审核
新书当前配置每章目标6000汉字、允许5500—6500，含前五章；已有书仍以该书正式state为准。启用opening_five_required时按docs/前五章投稿验收.md完成写前五章方案、同类样本与逐章累计审读。
如果本书已绑定reference_library，读取绑定参考库的最新catalog，按本章难题检索并回读真实来源，通过brief-request --references填写application与originality。写后在同一release报告的narrative_review.reference_use填写实际效果、原创性判断和本章引文；未接入新版的旧书沿用其真实配置，不追认旧章通过。
实际读取上章、最近三章全文、五章推进、相关旧事实与知情、资源和未兑现承诺；到期五章/阶段全文回看在采用前完成。按本书配置完成brief-request、干净任务书、场景预算、brief-check、全书相似办法检索及writer资料。context或tools_completed仅表示本批准备完成，按当前目标章的实际章长配置继续写完整章。有docs/开篇试写与剧情验收.md时按其规则验证实际结果。
可按任务书分3—5个有效场景连续写作，保存同章工作稿再合成全文。不能仅因准备完成、草稿暂不足字数或尚未审核就主动结束本轮；不得灌水、降字数或批填pass赶完成。每个实质检查点保存drafts中本章进度文件，记录真实run_id、阶段、草稿路径/哈希/实测字数、已完成场景及下一步；接续时回读稿件与result验证，进度文件不冒充采用证据。
实际生成并阅读reader资料，完成正文反向提纲、限信息审读、人物主动性、对立方行动、真实变化、兑现与续读理由、八项带引文审核和反重复；同上下文标same_context_approximation。最多3轮局部修订，不改冻结章、不重置计数。候选、record和真实release报告放drafts，经command核验；既有未完稿只续写同一章。

五、以章节证据验收
finalize统一执行release-check→adopt冻结→daily_update.py finish→workflow与索引；读取对应result、实际提交、正式正文与记录、完成回执及哈希。只有business_status=chapter_completed且远端回读全部匹配才输出“本轮章节已完成”。任务平台completed、Actions绿色、预检通过或tools_completed都不能代替章节完成。
真实故障、执行限制或审核无法通过时保留稿件和原目标；在确实持有本轮执行权时block并回读，输出“本轮章节未完成”，列最后完成阶段、真实原因/原始错误、检查点、原目标和下一步。单次网络或工具失败不得自行暂停长期计划，不改时间、不建替代任务。工具未提供自动续跑能力时不能声称已安排补跑；下一次合法运行继续原目标，不跳章。
反馈给真实任务ID、目标章、run_id、实测字数、采用状态及证据链接。实际模型和思考档位取不到时标未验证，不靠提示词宣称6.1或最高档。不自动投稿、签约、购买额度或调用外部AI API，不要求登录云浏览器；平台发布另凭真实回执登记。`;

export function dailyTaskPrompt(entry){return `${taskLocator(entry)}\n\n${DAILY_EXECUTION_RULES}`;}

export function writingPrompt(entry,management){
  const locator=taskLocator(entry),time=String(entry.expected_time||'');
  fail(/^([01]\d|2[0-3]):[0-5]\d$/.test(time),'每天执行时间无效。');
  const feedback=entry.feedback_url?validateChatURL(entry.feedback_url):'';
  const manager=management?parseRepository(management).url:'管理仓库未设置';
  return `请为本书建立或更新唯一的每日写作任务：每天北京时间（Asia/Shanghai）${time}执行。\n${locator}

【本次配置，不保存为每日执行内容】
先读本书最新状态与.automation/config.json，私下按仓库、book_id和已有任务ID查找同书任务；已有就复用，不另建。查不到或身份不一致时核实具体缺口，不在未确定没有同书有效任务时另建。保持既有反馈绑定，不承诺一定返回创建聊天。${feedback?'已登记反馈链接：'+feedback+'；须核对真实绑定。':''}
仅将下方两个标记之间的长期指令保存为任务prompt；只用实测身份补齐缺失book_id，不把本次配置步骤、当前章次、临时草稿路径、旧锁编号、运行结果或聊天总结写成永久状态。每次执行仍须重新读GitHub。
实际核对任务ID、启用状态、时区、日程、下次时间及反馈对话；平台没有返回的字段写未验证，不自行编造。将真实绑定写入本书配置，保留原completion_policy等既有字段。旧书缺固定工具时按 ${SYSTEM_REPOSITORY} 的旧书接入说明审查合并，不复制state、不解冻或追认旧章。
做一次不写章的preflight并回读对应作业与result。配置反馈分开报告“任务配置已核对”“工具预检通过”“完整日更已实测/待实测”；预检通过不能宣称稳定日更或章节已写成。本条仅配置计划，不为测试自动写章、抢锁、另建补跑任务或改变本书质量门槛。

【长期任务指令开始】
${dailyTaskPrompt(entry)}
【长期任务指令结束】

${manager} 的勾选仅控制今日更新查询，不是本书写作授权或完成证据；查询仍按最新正式章节文件最近提交的北京时间日期判断，不加日报/回执门槛。`;
}

export function repairPrompt(entry){
  return `请现在核查并接续本书当前未完成的一个目标章，不改每日计划。\n${taskLocator(entry)}
先读取AGENTS.md、docs/定时执行器.md、最新state/workflow、book/daily/active.json、草稿进度及完成回执。已经完成且证据齐全就报告无需补更并停止，不新开下一章；回执缺失按recovered_completion恢复证据。先区分已有授权的operator_recovery.status=ready维护检查点与普通旧锁；普通旧锁须核实原控制者确切平台运行终态与全部关联执行器作业终态，未知旧running不超时抢占。
若在普通聊天中收到本指令，先peek核对.automation/config.json绑定的唯一任务。确认确有未完目标，且已核实原运行与作业终态或已有合法ready维护检查点后，优先使用平台提供的原任务“立即运行”入口执行一次，复用本书唯一任务与固定执行器，不另建、不改日程。入口未提供、任务未启用或调用被拒绝时如实报告，不伪装定时运行的automation controller，不手改锁或借用旧session。请求成功只报告“已发起补更”；只有这次新运行的实际结果与对应GitHub章节证据匹配才能报告完成，不把旧一轮结果当作本次结果。
若本消息本来就在原任务的实际运行内，使用本轮真实controller按现行协议preflight→begin；普通另一轮须提供stopped_evidence合法恢复同一目标。若active.operator_recovery.status为ready，只核验已有维护授权；只有begin返回resumed且recovery_mode=operator_revocation才以本轮新run_id接续原章。不自行recover或制作维护授权，不删除锁、候选或返修次数。

实际执行补更时沿用以下逐阶段写作与验收规则，不把规则本身另建为任务：
${DAILY_EXECUTION_RULES}`;
}

export function checkerPrompt(management,branch){
  return `可选：请在本聊天建立每天北京时间20:00执行的查询任务；必须实际创建成功才报告启用状态和下次运行时间。\n每次读取 ${management} 的 ${branch||'默认分支'} 最新books.json，查询所有enabled=true的小说，不受expected_time、effective_from或宽限时间限制。按最新正式章节文件的最近一次Git提交日期（Asia/Shanghai）判断今天是否更新；只有改配置、改报告不能算更新。读取失败标unknown，不能算未更新。\n程序位于通用系统仓库 ${SYSTEM_REPOSITORY}。固定其提交后下载tools/query_today.mjs及web/dist/today-query.mjs、query-model.mjs、hub-core.mjs、core.mjs、github-transport.mjs，保留相对目录。程序只读模式不需要GPT API Key；公开查询正常路径使用Git版本发现、公开原文和章节文件历史，不依赖匿名REST调用。\n运行node tools/query_today.mjs --management ${management} --branch ${branch||'main'} --output /tmp/today-result.json。已有正确GitHub管理仓库写入授权时可用--write及仅在环境内的NOVEL_HUB_GITHUB_TOKEN，把最近7天查询观察保存到books.json；仅有GitHub连接器时按相同规则读取真实章节日期，原子比较books.json版本并写回query_history。保存前核对文件版本，冲突不覆盖。未实际写回并回读成功不能宣称已记录。不得打开别的小说聊天、代写下一章或到小说平台发布。`;
}
