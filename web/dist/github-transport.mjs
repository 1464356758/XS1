// Browser requests use the site's relay when present. CLI and injected test
// fetchers stay direct. No credential is placed in a URL or persistent storage.
export function createGitHubTransport({fetcher=globalThis.fetch,origin=globalThis.location?.origin,required=false}={}){
  let available;
  const endpoint=origin&&/^https?:\/\//.test(origin)?new URL('/api/github',origin):null;
  async function hasRelay(){
    if(!endpoint)return false;
    if(required)return true;
    if(!available)available=(async()=>{
      const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),4000);
      try{const u=new URL(endpoint);u.searchParams.set('health','1');const r=await fetcher(u.href,{signal:controller.signal,cache:'no-store',credentials:'same-origin',redirect:'error',referrerPolicy:'no-referrer'});if(!r.ok||!r.headers.get('content-type')?.includes('application/json'))return false;const data=await r.json();return data.service==='novel-github-relay-v1'&&data.protocol===1;}catch{return false;}finally{clearTimeout(timer);}
    })();
    return available;
  }
  return async(url,options={})=>{
    if(!await hasRelay())return fetcher(url,options);
    const u=new URL(endpoint);u.searchParams.set('target',url);
    // An ambiguous write is never retried through another connection.
    return fetcher(u.href,{...options,credentials:'same-origin',redirect:'error',referrerPolicy:'no-referrer'});
  };
}

let browserTransport;
export function githubFetch(url,options){
  if(typeof document==='undefined')return globalThis.fetch(url,options);
  browserTransport??=createGitHubTransport({required:document.querySelector('meta[name="novel-github-transport"]')?.content==='relay'});
  return browserTransport(url,options);
}

// Parse the public smart-HTTP v0 advertisement. This is an actual commit SHA,
// never a raw-file ETag or an index's generated_at value.
export function parseGitRefs(text){
  const bytes=new TextEncoder().encode(text),decode=new TextDecoder('utf-8',{fatal:true}),refs={};let at=0,defaultBranch='';
  while(at<bytes.length){
    const prefix=decode.decode(bytes.slice(at,at+4));if(!/^[a-fA-F0-9]{4}$/.test(prefix))throw new Error('无效Git版本记录');
    const n=parseInt(prefix,16);at+=4;if(n===0||n===1||n===2)continue;
    if(n<4||at+n-4>bytes.length)throw new Error('Git版本记录不完整');
    const line=decode.decode(bytes.slice(at,at+n-4));at+=n-4;
    if(line.startsWith('# service=git-upload-pack'))continue;
    const [value,caps='']=line.replace(/\n$/,'').split('\0'),match=/^([a-f0-9]{40}) (HEAD|refs\/(?:heads|tags)\/[^\s]+)$/.exec(value);
    if(match)refs[match[2]]=match[1];
    const symref=/(?:^| )symref=HEAD:refs\/heads\/([^ ]+)/.exec(caps);if(symref)defaultBranch=symref[1];
  }
  if(!refs.HEAD)throw new Error('公开仓库尚无可读取提交');
  return {refs,defaultBranch};
}

export function parseCommitFeed(text){
  if(typeof text!=='string'||text.includes('<!DOCTYPE')||!/<feed\b/.test(text))throw new Error('章节文件历史格式无效。');
  const start=text.search(/<entry\b/),prefix=start<0?text:text.slice(0,start),sourceId=/<id>\s*([^<]+)\s*<\/id>/.exec(prefix)?.[1]?.trim();
  const entry=/<entry\b[^>]*>([\s\S]*?)<\/entry>/.exec(text)?.[1];if(!entry)throw new Error('章节文件没有可读取的提交记录。');
  const commit=/<id>\s*tag:github\.com,2008:Grit::Commit\/([a-f0-9]{40})\s*<\/id>/.exec(entry)?.[1],date=/<updated>\s*([^<]+)\s*<\/updated>/.exec(entry)?.[1]?.trim();
  if(!commit||!date||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(date)||!Number.isFinite(Date.parse(date)))throw new Error('章节提交日期无效。');
  return {commit,date,sourceId};
}
