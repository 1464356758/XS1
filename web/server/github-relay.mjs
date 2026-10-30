// Shared by Sites Worker and the optional Netlify function. No stored tokens,
// redirects, arbitrary upstream hosts, cookies, or user-controlled log output.
const RELAY='novel-github-relay-v1',LIMIT=4000000,BODY_LIMIT=1000000;
class RelayError extends Error{constructor(status,code){super(code);this.status=status;this.code=code;}}
const check=(ok,status=400,code='invalid_request')=>{if(!ok)throw new RelayError(status,code);};
function reply(body,status=200,type='application/json; charset=utf-8',extra={}){return new Response(body,{status,headers:{'Content-Type':type,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Novel-Relay':'1',...extra}});}
function errorReply(status,code){return reply(JSON.stringify({error:code}),status,undefined,{'X-Novel-Error':code});}
async function limitedText(response,limit){
  check(Number(response.headers.get('content-length')||0)<=limit,413,'too_large');
  if(!response.body)return '';
  const reader=response.body.getReader(),chunks=[];let size=0;
  while(true){const item=await reader.read();if(item.done)break;size+=item.value.length;if(size>limit){await reader.cancel();throw new RelayError(413,'too_large');}chunks.push(item.value);}
  const bytes=new Uint8Array(size);let at=0;for(const chunk of chunks){bytes.set(chunk,at);at+=chunk.length;}
  try{return new TextDecoder('utf-8',{fatal:true}).decode(bytes);}catch{throw new RelayError(502,'invalid_encoding');}
}
function targetURL(value,method){
  check(typeof value==='string'&&value.length<=3000&&!/%(?:00|0a|0d|5c|25)/i.test(value));
  let u;try{u=new URL(value);}catch{throw new RelayError(400,'invalid_target');}
  check(u.protocol==='https:'&&!u.username&&!u.password&&!u.port&&!u.hash,400,'invalid_target');
  check(!value.includes('\\')&&!/%2e/i.test(value)&&!/(?:^|\/)\.{1,2}(?:\/|$)/.test(value.split('?')[0]),400,'invalid_target');
  const api=u.hostname==='api.github.com',raw=u.hostname==='raw.githubusercontent.com',git=u.hostname==='github.com';
  check(api||raw||git,400,'invalid_target');
  const parts=u.pathname.split('/').slice(1).map(p=>{try{return decodeURIComponent(p);}catch{throw new RelayError(400,'invalid_target');}});
  const identifier=s=>typeof s==='string'&&/^[A-Za-z0-9_.-]+$/.test(s)&&s!=='.'&&s!=='..';
  check(identifier(parts[api?1:0])&&identifier(parts[api?2:1]),400,'invalid_target');
  if(git){
    if(parts[2]==='commits'){check(method==='GET'&&!u.search&&parts.length===7&&/^[a-f0-9]{40}$/.test(parts[3])&&parts[4]==='book'&&parts[5]==='chapters'&&/^CH\d{3,6}_[a-f0-9]{64}\.txt\.atom$/.test(parts[6]),400,'invalid_target');return {u,raw:true,history:true};}
    check(method==='GET'&&parts.length===4&&parts[1].endsWith('.git')&&parts[2]==='info'&&parts[3]==='refs'&&u.search==='?service=git-upload-pack',400,'invalid_target');return {u,raw:true,git:true};
  }
  if(raw){check(method==='GET'&&!u.search&&/^[a-f0-9]{40}$/.test(parts[2])&&parts.length>3,400,'invalid_target');check(parts.slice(3).every(p=>p&&p!=='.'&&p!=='..'&&!/[\\\x00-\x1f]/.test(p)),400,'invalid_target');return {u,raw:true};}
  check(parts[0]==='repos',400,'invalid_target');
  const path=parts.slice(3).join('/');
  if(method==='GET'){
    const allowed=path===''||path==='commits'||/^commits\/[A-Za-z0-9_][A-Za-z0-9_.\/-]*$/.test(path)||/^git\/commits\/[a-f0-9]{40}$/.test(path)||/^contents\/.+/.test(path);
    check(allowed&&!path.includes('..')&&!path.includes('//'),400,'invalid_target');
    const keys=path==='commits'?['path','per_page','sha']:path.startsWith('contents/')?['ref']:[];
    for(const [k,v] of u.searchParams){check(keys.includes(k)&&u.searchParams.getAll(k).length===1&&v.length<=500,400,'invalid_target');if(k==='per_page')check(/^[1-9]\d?$/.test(v),400,'invalid_target');if(k==='ref')check(/^[a-f0-9]{40}$/.test(v),400,'invalid_target');}
  }else{
    check(!u.search&&((method==='PUT'&&path==='contents/books.json')||(method==='POST'&&['git/blobs','git/trees','git/commits'].includes(path))||(method==='PATCH'&&/^git\/refs\/heads\/[A-Za-z0-9_][A-Za-z0-9_.\/-]*$/.test(path)&&!path.includes('..'))),405,'method_not_allowed');
  }
  return {u,raw:false,path};
}
function validateWrite(path,body){
  check(body&&typeof body==='object'&&!Array.isArray(body));
  const sha=s=>typeof s==='string'&&/^[a-f0-9]{40}$/.test(s);
  if(path==='contents/books.json')check(typeof body.content==='string'&&/^[A-Za-z0-9+/]*={0,2}$/.test(body.content)&&typeof body.message==='string'&&typeof body.branch==='string'&&/^[A-Za-z0-9_][A-Za-z0-9_.\/-]*$/.test(body.branch)&&!body.branch.includes('..')&&(body.sha===undefined||sha(body.sha)),400,'invalid_write_scope');
  if(path==='git/blobs')check(body.encoding==='utf-8'&&typeof body.content==='string');
  if(path==='git/trees')check(sha(body.base_tree)&&Array.isArray(body.tree)&&body.tree.length===1&&body.tree.every(x=>x.path==='books.json'&&x.mode==='100644'&&x.type==='blob'&&sha(x.sha)),400,'invalid_write_scope');
  if(path==='git/commits')check(sha(body.tree)&&Array.isArray(body.parents)&&body.parents.length===1&&sha(body.parents[0])&&typeof body.message==='string');
  if(path.startsWith('git/refs/'))check(sha(body.sha)&&body.force===false,400,'force_not_allowed');
}
export async function handleGitHubRelay(request,{fetcher=globalThis.fetch,allowWrites=true}={}){
  let timer;
  try{
    const own=new URL(request.url),origin=request.headers.get('origin');
    check(!origin||origin===own.origin,403,'origin_not_allowed');
    check(request.headers.get('sec-fetch-site')!=='cross-site',403,'origin_not_allowed');
    if(own.searchParams.get('health')==='1'&&!own.searchParams.has('target')){check(request.method==='GET',405,'method_not_allowed');return reply(JSON.stringify({service:RELAY,protocol:1,write:allowWrites}));}
    check([...own.searchParams.keys()].every(k=>k==='target')&&own.searchParams.getAll('target').length===1);
    const method=request.method,{u,raw,path,history}=targetURL(own.searchParams.get('target'),method);
    const controller=new AbortController();timer=setTimeout(()=>controller.abort(),15000);
    const headers={Accept:request.headers.get('accept')==='application/vnd.github.raw+json'?'application/vnd.github.raw+json':'application/vnd.github+json','User-Agent':'Novel-Workspace/1.0.1'};
    let body;
    if(method!=='GET'){
      check(allowWrites,405,'read_only');check(origin===own.origin,403,'origin_required');
      check(request.headers.get('content-type')?.split(';')[0]==='application/json',415,'json_required');
      const authorization=request.headers.get('authorization')||'';check(/^Bearer [A-Za-z0-9_\-.]{10,300}$/.test(authorization),401,'auth_required');
      body=await limitedText(request,BODY_LIMIT);let parsed;try{parsed=JSON.parse(body);}catch{throw new RelayError(400,'invalid_json');}validateWrite(path,parsed);
      headers.Authorization=authorization;headers['Content-Type']='application/json';headers['X-GitHub-Api-Version']='2026-03-10';
    }
    // Only the client configured for the management repo has a token. Novel,
    // raw-file and Git-refs reads remain anonymous; cookies are never forwarded.
    if(method==='GET'&&!raw&&request.headers.has('authorization')){
      const authorization=request.headers.get('authorization');check(/^Bearer [A-Za-z0-9_\-.]{10,300}$/.test(authorization),401,'auth_required');headers.Authorization=authorization;headers['X-GitHub-Api-Version']='2026-03-10';
    }
    const upstream=await fetcher(u.href,{method,headers:raw?{'User-Agent':headers['User-Agent'],...(history?{Accept:'application/atom+xml'}:{})}:headers,body,signal:controller.signal,redirect:'manual',credentials:'omit',cache:'no-store'});
    if(upstream.status>=300&&upstream.status<400){upstream.body?.cancel();return errorReply(502,'upstream_redirect');}
    if(!upstream.ok){upstream.body?.cancel();const h={};for(const k of ['retry-after','x-ratelimit-remaining','x-ratelimit-reset'])if(upstream.headers.has(k))h[k]=upstream.headers.get(k);const code=upstream.status===404?'not_found':upstream.status===401?'auth':upstream.status===403||upstream.status===429?'rate_limit':upstream.status===409||upstream.status===422?'conflict':'upstream_error';return reply(JSON.stringify({error:code}),upstream.status,undefined,{'X-Novel-Error':code,...h});}
    const text=await limitedText(upstream,LIMIT);
    return reply(text,upstream.status,raw||headers.Accept==='application/vnd.github.raw+json'?'text/plain; charset=utf-8':'application/json; charset=utf-8');
  }catch(e){if(e instanceof RelayError)return errorReply(e.status,e.code);return errorReply(e.name==='AbortError'?504:502,e.name==='AbortError'?'upstream_timeout':'upstream_network');}
  finally{clearTimeout(timer);}
}
