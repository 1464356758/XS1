import test from 'node:test';
import assert from 'node:assert/strict';
import {GitHubClient} from '../dist/hub-core.mjs';
import {createGitHubTransport,parseGitRefs} from '../dist/github-transport.mjs';
import {handleGitHubRelay} from '../server/github-relay.mjs';

const origin='https://novel.example',api='https://api.github.com/repos/example/novel',commit='a'.repeat(40);
const at=(target,options={})=>new Request(origin+'/api/github?target='+encodeURIComponent(target),options);
const json=value=>new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});

test('raw connection failure falls back to Contents at the same immutable commit',async()=>{
  const requests=[],client=new GitHubClient('example/novel',{token:'TEST_ONLY_SECRET',fetcher:async(url,opts)=>{requests.push({url,opts});if(url.includes('raw.githubusercontent.com'))throw new TypeError('connection failed');return new Response('真实格式正文\r\n');}});
  const file=await client.readFile('book/chapters/example.txt',commit);
  assert.equal(file.text,'真实格式正文\n');assert.equal(requests.length,2);
  assert.equal(requests[1].url,api+'/contents/book/chapters/example.txt?ref='+commit);
  assert.equal(requests[1].opts.headers.Accept,'application/vnd.github.raw+json');
  assert.equal(requests[1].opts.headers.Authorization,undefined);
});
test('a confirmed file absence remains not_found after checking the alternate source',async()=>{
  let requests=0;const client=new GitHubClient('example/novel',{fetcher:async()=>{requests++;return new Response('{}',{status:404});}});
  assert.equal(await client.optionalJSON('book/daily/2026-10-26.json',commit),null);assert.equal(requests,2);
});
test('invalid file encoding is never replaced by a different source',async()=>{
  let requests=0;const client=new GitHubClient('example/novel',{fetcher:async()=>{requests++;return new Response(new Uint8Array([255]));}});
  await assert.rejects(client.readFile('books.json',commit),e=>e.code==='encoding');assert.equal(requests,1);
});
test('required relay keeps browser traffic at the site origin',async()=>{
  const requests=[],transport=createGitHubTransport({origin,required:true,fetcher:async(url,opts)=>{requests.push({url,opts});return json({sha:commit});}});
  await transport(api+'/commits/HEAD',{method:'GET',credentials:'omit',headers:{Accept:'application/vnd.github+json'}});
  assert.equal(new URL(requests[0].url).origin,origin);assert.equal(new URL(requests[0].url).searchParams.get('target'),api+'/commits/HEAD');assert.equal(requests[0].opts.credentials,'same-origin');
});
test('static hosting uses direct requests if it has no relay',async()=>{
  const requests=[],transport=createGitHubTransport({origin,fetcher:async(url)=>{requests.push(url);return url.startsWith(origin)?new Response('<html>static fallback</html>',{headers:{'Content-Type':'text/html'}}):json({sha:commit});}});
  await transport(api);await transport(api+'/commits/HEAD');
  assert.equal(requests.filter(x=>x.startsWith(origin)).length,1);assert.deepEqual(requests.slice(1),[api,api+'/commits/HEAD']);
});
test('Netlify-style health detection selects the relay once',async()=>{
  const requests=[],transport=createGitHubTransport({origin,fetcher:async(url)=>{requests.push(url);return json(url.includes('health=1')?{service:'novel-github-relay-v1',protocol:1}:{});}});
  await Promise.all([transport(api),transport(api+'/commits/HEAD')]);assert.equal(requests.filter(x=>x.includes('health=1')).length,1);assert.ok(requests.every(x=>new URL(x).origin===origin));
});
test('an ambiguous write failure is not retried or sent directly',async()=>{
  let count=0;const transport=createGitHubTransport({origin,required:true,fetcher:async()=>{count++;throw new TypeError('connection lost after submission');}});
  await assert.rejects(transport(api+'/git/refs/heads/main',{method:'PATCH',headers:{Authorization:'Bearer TEST_ONLY_SECRET'}}));assert.equal(count,1);
});
test('relay health discloses capabilities without contacting GitHub',async()=>{
  const r=await handleGitHubRelay(new Request(origin+'/api/github?health=1'),{allowWrites:false,fetcher:()=>{throw new Error('must not fetch');}});
  assert.deepEqual(await r.json(),{service:'novel-github-relay-v1',protocol:1,write:false});
});
test('relay rejects arbitrary hosts traversal and non-repository endpoints',async()=>{
  const targets=['https://evil.example/repos/example/novel', 'http://api.github.com/repos/example/novel','https://api.github.com/user','https://api.github.com/repos/example/novel/../../user',api+'/contents/%2e%2e/secrets?ref='+commit,api+'/issues','https://raw.githubusercontent.com/example/novel/HEAD/books.json',api+'?token=TEST_ONLY_SECRET'];
  for(const target of targets){let fetched=false;const r=await handleGitHubRelay(at(target),{fetcher:async()=>{fetched=true;return json({});}});assert.equal(r.status,400,target);assert.equal(fetched,false);}
});
test('anonymous public reads do not gain credential or cookie headers',async()=>{
  let sent;const r=await handleGitHubRelay(at(api+'/commits/HEAD',{headers:{Cookie:'secret-cookie'}}),{fetcher:async(url,opts)=>{sent={url,opts};return json({sha:commit});}});
  assert.equal(r.status,200);assert.equal(sent.opts.headers.Authorization,undefined);assert.equal(sent.opts.headers.Cookie,undefined);assert.equal(sent.opts.redirect,'manual');assert.equal(sent.opts.credentials,'omit');
});
test('management API reads can use their explicitly provided scoped token',async()=>{
  let sent;const r=await handleGitHubRelay(at(api+'/git/commits/'+commit,{headers:{Authorization:'Bearer TEST_ONLY_SECRET'}}),{fetcher:async(url,opts)=>{sent=opts;return json({tree:{sha:commit}});}});
  assert.equal(r.status,200);assert.equal(sent.headers.Authorization,'Bearer TEST_ONLY_SECRET');
});
test('raw relay response is plain text and does not gain credential headers',async()=>{
  const target='https://raw.githubusercontent.com/example/novel/'+commit+'/book/chapters/CH001.txt';let sent;
  const r=await handleGitHubRelay(at(target),{fetcher:async(url,opts)=>{sent=opts;return new Response('正文\n');}});
  assert.equal(r.headers.get('content-type'),'text/plain; charset=utf-8');assert.equal(await r.text(),'正文\n');assert.equal(sent.headers.Authorization,undefined);
});
test('relay does not follow redirects or echo upstream bodies',async()=>{
  const redirected=await handleGitHubRelay(at(api),{fetcher:async()=>new Response('TEST_ONLY_SECRET',{status:302,headers:{Location:'https://evil.example/'}})});
  assert.equal(redirected.status,502);assert.equal(redirected.headers.get('x-novel-error'),'upstream_redirect');assert.ok(!(await redirected.text()).includes('TEST_ONLY_SECRET'));
  const denied=await handleGitHubRelay(at(api),{fetcher:async()=>new Response('TEST_ONLY_SECRET',{status:403})});assert.equal(denied.status,403);assert.ok(!(await denied.text()).includes('TEST_ONLY_SECRET'));
});
test('relay distinguishes upstream network errors from a missing repository',async()=>{
  const r=await handleGitHubRelay(at(api),{fetcher:async()=>{throw new TypeError('TEST_ONLY_SECRET');}});assert.equal(r.status,502);assert.equal(r.headers.get('x-novel-error'),'upstream_network');
});
test('writes require the same origin and a user credential; partner relay is read only',async()=>{
  const options={method:'PATCH',headers:{Origin:origin,'Content-Type':'application/json',Authorization:'Bearer TEST_ONLY_SECRET'},body:JSON.stringify({sha:commit,force:false})};
  for(const [change,status] of [[{headers:{...options.headers,Origin:'https://other.example'}},403],[{headers:{...options.headers,Authorization:''}},401],[{headers:{...options.headers,Origin:''}},403]]){const r=await handleGitHubRelay(at(api+'/git/refs/heads/main',{...options,...change}));assert.equal(r.status,status);}
  const r=await handleGitHubRelay(at(api+'/git/refs/heads/main',options),{allowWrites:false});assert.equal(r.status,405);
});
test('only non-force reference updates are forwarded and their token stays in a header',async()=>{
  let sent;const options={method:'PATCH',headers:{Origin:origin,'Content-Type':'application/json',Authorization:'Bearer TEST_ONLY_SECRET'},body:JSON.stringify({sha:commit,force:false})};
  const r=await handleGitHubRelay(at(api+'/git/refs/heads/main',options),{fetcher:async(url,opts)=>{sent={url,opts};return json({ref:'refs/heads/main'});}});
  assert.equal(r.status,200);assert.equal(sent.opts.headers.Authorization,'Bearer TEST_ONLY_SECRET');assert.ok(!sent.url.includes('TEST_ONLY_SECRET'));assert.equal(JSON.parse(sent.opts.body).force,false);
  const force=await handleGitHubRelay(at(api+'/git/refs/heads/main',{...options,body:JSON.stringify({sha:commit,force:true})}));assert.equal(force.status,400);
});
test('relay tree mutation is restricted to books.json with a preserved base tree',async()=>{
  const make=tree=>at(api+'/git/trees',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json',Authorization:'Bearer TEST_ONLY_SECRET'},body:JSON.stringify(tree)});
  let count=0;const fetcher=async()=>{count++;return json({sha:commit});};
  const good={base_tree:commit,tree:[{path:'books.json',mode:'100644',type:'blob',sha:commit}]};assert.equal((await handleGitHubRelay(make(good),{fetcher})).status,200);
  assert.equal((await handleGitHubRelay(make({...good,tree:[{...good.tree[0],path:'book/state.json'}]}),{fetcher})).status,400);assert.equal(count,1);
});
test('upstream payloads exceeding the cap are stopped',async()=>{
  const r=await handleGitHubRelay(at(api),{fetcher:async()=>new Response('small',{headers:{'Content-Length':'5000000'}})});assert.equal(r.status,413);
});

const packet=s=>(new TextEncoder().encode(s).length+4).toString(16).padStart(4,'0')+s;
const refs=()=>packet('# service=git-upload-pack\n')+'0000'+packet(commit+' HEAD\0multi_ack symref=HEAD:refs/heads/main object-format=sha1\n')+packet(commit+' refs/heads/main\n')+packet('b'.repeat(40)+' refs/heads/feature/novel\n')+'0000';
test('public Git discovery yields the real HEAD default branch and named branches',()=>{
  const git=parseGitRefs(refs());assert.equal(git.refs.HEAD,commit);assert.equal(git.defaultBranch,'main');assert.equal(git.refs['refs/heads/feature/novel'],'b'.repeat(40));
  assert.throws(()=>parseGitRefs('not a git response'));assert.throws(()=>parseGitRefs(refs().slice(0,-10)));assert.throws(()=>parseGitRefs(packet('# service=git-upload-pack\n')+'0000'));
});
test('anonymous API rate limit does not prevent resolving a pinned public snapshot',async()=>{
  const requests=[],client=new GitHubClient('example/novel',{fetcher:async(url)=>{requests.push(url);return url.includes('/info/refs?')?new Response(refs()):new Response('{}',{status:403});}});
  assert.equal((await client.publicInfo()).default_branch,'main');assert.equal((await client.snapshot()).commit,commit);assert.equal((await client.snapshot('feature/novel')).commit,'b'.repeat(40));
  assert.ok(requests.some(x=>x==='https://github.com/example/novel.git/info/refs?service=git-upload-pack'));
  await assert.rejects(client.snapshot('missing'),e=>e.code==='not_found');
});
test('relay permits only anonymous read-only Git reference discovery',async()=>{
  const target='https://github.com/example/novel.git/info/refs?service=git-upload-pack';let sent;
  const r=await handleGitHubRelay(at(target,{headers:{Authorization:'Bearer TEST_ONLY_SECRET'}}),{fetcher:async(url,opts)=>{sent=opts;return new Response(refs());}});assert.equal(r.status,200);assert.equal(parseGitRefs(await r.text()).refs.HEAD,commit);assert.equal(sent.headers.Authorization,undefined);
  for(const value of [target.replace('git-upload-pack','git-receive-pack'),target.replace('/info/refs','/archive/main.zip')])assert.equal((await handleGitHubRelay(at(value))).status,400);
});

test('default and HEAD snapshots carry the real branch so progress follows a default branch switch',async()=>{
 let branch='main';const requests=[],advertisement=()=>packet('# service=git-upload-pack\n')+'0000'+packet(commit+' HEAD\0symref=HEAD:refs/heads/'+branch+'\n')+packet(commit+' refs/heads/'+branch+'\n')+'0000';
 const client=new GitHubClient('example/novel',{preferGit:true,fetcher:async url=>{requests.push(url);return new Response(advertisement());}});
 assert.equal((await client.snapshot()).branch,'main');assert.equal((await client.snapshot('HEAD')).branch,'main');assert.equal((await client.snapshot('main')).branch,'main');
 branch='next';assert.equal((await client.snapshot()).branch,'next');assert.ok(requests.every(url=>url.includes('/info/refs?')));
 const fallback=new GitHubClient('example/novel',{fetcher:async url=>url.includes('/info/refs?')?new Response(advertisement()):new Response('{}',{status:403})});
 assert.equal((await fallback.snapshot()).branch,'next');
});
