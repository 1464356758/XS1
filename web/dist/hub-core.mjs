import {parseRepository, validateManifest, sha256, canonicalJSON, ReaderError} from './core.mjs';
import {githubFetch,parseGitRefs,parseCommitFeed} from './github-transport.mjs';
import {normalizeQueryHistory} from './query-model.mjs';
export {parseRepository, sha256, canonicalJSON};

export const HUB_VERSION='1.4.0';
export const SYSTEM_REPOSITORY='https://github.com/1464356758/xiaishuo-ZUOZONG';
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
      if(active.status==='blocked')return {...result,status:'blocked',label:'执行已记录中断',reason:active.reason||'核实原执行停止后，继续原目标章。'};
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
export function writingPrompt(entry,management){
  return `为《${entry.title}》建立或更新唯一的每日写作任务：每天北京时间（Asia/Shanghai）${entry.expected_time}执行。先按仓库链接与作品身份查询已有定时任务；已有就复用、更新，不能每天另建。实际创建后核对启用状态、任务编号、下次执行时间和实际反馈对话。用户接受固定的任务反馈对话，后续沿用该任务，不承诺一定返回创建时的原聊天。${entry.feedback_url?'已登记反馈链接：'+entry.feedback_url+'；仍须核对实际任务绑定。':''}若工具无法指定对话或读取模型及思考档位，明确记为未验证，不能以提示词声称已切成6.1或最高档，也不要求用户登录云浏览器。\n本书唯一事实源：${entry.repository_url} 的${entry.branch||'默认分支'}。${entry.book_id?'预期作品身份：'+entry.book_id+'。':''}反馈聊天仅供查看，正文与进度以GitHub为准。先读AGENTS.md、docs/每日自动更新.md和本书每日一章指令。旧书缺工具时按 ${SYSTEM_REPOSITORY} 的docs/旧书接入工作台.md核对合并升级，不复制母版state、不追认旧章通过、不擅自启用冻结。\n每次运行 daily_update.py begin 固定目标。already_completed停止重复；verify_in_progress先核实旧执行，实际停止后才能恢复；recovered_completion先同步恢复回执，不顺便写下一章。首次或恢复begin后，先按预期分支头原子保存执行记录并回读，再开始写作。\n实际读取上章、最近三章全文、五章推进、相关事实与人物知情、开放承诺；到期五章及阶段全文回看在采用前完成。先登记干净任务书与场景预算，检索全书相似办法并回查原文，按本书字数写完整目标一章。写后从正文提取真实选择、代价和变化，再完成限信息审读与带引文审核；不得用摘要代替正文、批量填pass或降低门槛。只作必要局部修订，最多3轮，不重置计数，不改冻结章。\n通过release-check并adopt后，运行 daily_update.py finish --run-id 本次编号，重建并验证online/index.json；正文、事实记录、审查、状态、执行回执与索引同批非强制写回。提交前再查远端执行编号与分支头，旧执行不能覆盖新执行。回读实际提交的正文、状态和回执，成功才报告“已保存”。失败保留同一目标，能记录时block真实原因并写回；未通过不能假装完成。\n${management||'管理仓库未设置'} 的勾选仅控制查询；停写需暂停实际任务。每日完成、章节文件今天更新、平台已发布分开记录；不自动投稿、不购买额度。`;
}
export function repairPrompt(entry){return `恢复 ${entry.repository_url} 的最新正式状态，先读AGENTS.md和docs/每日自动更新.md。检查今天完成回执和book/daily/active.json。已完成就结束；还在运行或状态不明先核实，不并行生成同一章。原执行已确认停止后，使用daily_update.py begin --resume-stopped恢复同一目标，不重置原修订次数，不另起下一章。实际完成检查、采用后finish，重建索引，原子写回并回读。不能以聊天回复替代仓库完成证据。`;}
export function checkerPrompt(management,branch){
  return `可选：请在本聊天建立每天北京时间20:00执行的查询任务；必须实际创建成功才报告启用状态和下次运行时间。\n每次读取 ${management} 的 ${branch||'默认分支'} 最新books.json，查询所有enabled=true的小说，不受expected_time、effective_from或宽限时间限制。按最新正式章节文件的最近一次Git提交日期（Asia/Shanghai）判断今天是否更新；只有改配置、改报告不能算更新。读取失败标unknown，不能算未更新。\n程序位于通用系统仓库 ${SYSTEM_REPOSITORY}。固定其提交后下载tools/query_today.mjs及web/dist/today-query.mjs、query-model.mjs、hub-core.mjs、core.mjs、github-transport.mjs，保留相对目录。程序只读模式不需要GPT API Key；公开查询正常路径使用Git版本发现、公开原文和章节文件历史，不依赖匿名REST调用。\n运行node tools/query_today.mjs --management ${management} --branch ${branch||'main'} --output /tmp/today-result.json。已有正确GitHub管理仓库写入授权时可用--write及仅在环境内的NOVEL_HUB_GITHUB_TOKEN，把最近7天查询观察保存到books.json；仅有GitHub连接器时按相同规则读取真实章节日期，原子比较books.json版本并写回query_history。保存前核对文件版本，冲突不覆盖。未实际写回并回读成功不能宣称已记录。不得打开别的小说聊天、代写下一章或到小说平台发布。`;
}
