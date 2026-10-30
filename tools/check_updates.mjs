#!/usr/bin/env node
// 同一套确定性规则供网页和总检查任务使用；不调用模型。
import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {GitHubClient,HubError,parseRepository,safePath,validateRegistry,validateReport,inspectRegistry,loadRegistry,sha256} from '../web/dist/hub-core.mjs';

export class SnapshotClient {
  constructor(entry,source){
    this.repo=parseRepository(entry.repository_url);this.source=source;
    if(!source||parseRepository(source.repository_url).key!==this.repo.key||!/^[a-f0-9]{40}$/.test(source.commit)||!source.files||typeof source.files!=='object')throw new HubError('缺少按固定提交读取的仓库快照。');
    if(entry.branch&&entry.branch!==source.branch)throw new HubError('离线快照分支与清单不一致。');
  }
  async snapshot(){return {commit:this.source.commit,branch:this.source.branch,committed_at:this.source.committed_at||null};}
  async readFile(file,commit){
    safePath(file);if(commit!==this.source.commit)throw new HubError('快照提交不一致。');
    const value=this.source.files[file];
    if(value?.missing===true)throw new HubError('该提交下文件不存在。','not_found');
    if(!value||typeof value.text!=='string')throw new HubError('快照没有收集 '+file+'；不能将未读取当不存在。','incomplete_snapshot');
    const text=value.text.replace(/\r\n?/g,'\n');return {text,hash:await sha256(text)};
  }
  async readJSON(file,commit){const raw=await this.readFile(file,commit);return {...raw,data:JSON.parse(raw.text)};}
  async optionalJSON(file,commit){try{return await this.readJSON(file,commit);}catch(e){if(e.code==='not_found')return null;throw e;}}
}

export function preserveValidStates(report,previous){
  let old=new Map();try{if(previous){validateReport(previous);old=new Map(previous.results.map(r=>[r.id,r]));}}catch{}
  for(const r of report.results){
    if(r.commit&&Number.isInteger(r.chapters))r.last_valid_state={commit:r.commit,chapters:r.chapters,observed_at:r.checked_at};
    else if(old.get(r.id)?.last_valid_state)r.last_valid_state=old.get(r.id).last_valid_state;
    else if(old.get(r.id)?.commit&&Number.isInteger(old.get(r.id)?.chapters)){const x=old.get(r.id);r.last_valid_state={commit:x.commit,chapters:x.chapters,observed_at:x.checked_at};}
  }
  return report;
}
export function reportBundle(report,runId){
  if(!/^[a-zA-Z0-9_-]{8,100}$/.test(runId))throw new HubError('检查运行编号无效。');
  validateReport(report);report={...report,run_id:runId};
  const encode=x=>JSON.stringify(x,null,2)+'\n';
  const snapshot={schema_version:1,type:'novel-hub-snapshot-v1',date:report.date,checked_at:report.checked_at,registry_fingerprint:report.registry_fingerprint,
    books:report.results.map(r=>({id:r.id,status:r.status,commit:r.commit,chapters:r.chapters,last_valid_state:r.last_valid_state||null,evidence:r.evidence||null}))};
  const md='# 小说更新检查 '+report.date+'\n\n检查时间：'+report.checked_at+'。本报告仅核验正式仓库更新，不代表平台已发布或文学质量。\n\n'+report.results.map(r=>'- '+r.title.replace(/[\r\n]/g,' ')+'：'+r.status+'；'+r.reason.replace(/[\r\n]/g,' ')).join('\n')+'\n';
  return {[`reports/${report.date}/${runId}.json`]:encode(report),[`snapshots/${report.date}/${runId}.json`]:encode(snapshot),[`reports/${report.date}/${runId}.md`]:md,'reports/latest.json':encode(report)};
}
function options(argv){
  const o={};for(let i=0;i<argv.length;i++){const k=argv[i];if(k==='--write')o.write=true;else if(k==='--help')o.help=true;else if(['--management','--branch','--input','--output','--bundle','--run-id'].includes(k)){if(!argv[i+1]||argv[i+1].startsWith('--'))throw new HubError(k+' 缺少参数。');o[k.slice(2)]=argv[++i];}else throw new HubError('未知参数：'+k);}return o;
}
export async function run(argv){
  const o=options(argv);
  if(o.help){console.log('用法：node tools/check_updates.mjs --management https://github.com/owner/management [--branch main] [--output report.json] [--write]\n或：--input connector-snapshot.json --output report.json --bundle bundle.json\n--write 使用仅在环境中的 NOVEL_HUB_GITHUB_TOKEN；离线快照模式由 GitHub 工具按 bundle 和 guard 原子写回。');return;}
  let registry,previous=null,management,source,clientFactory,client;
  if(o.input){
    if(o.write)throw new HubError('离线模式不能直接 --write；请用 GitHub 工具核对 guard 后写入 bundle。');
    const input=JSON.parse(await fs.readFile(o.input,'utf8'));
    if(input.type!=='novel-hub-connector-input-v1'||typeof input.registry_text!=='string')throw new HubError('离线输入格式无效。');
    registry=validateRegistry(JSON.parse(input.registry_text));source={fileHash:await sha256(input.registry_text),head:input.management_commit,branch:input.management_branch};
    management=parseRepository(input.management_repository).url;
    if(!/^[a-f0-9]{40}$/.test(source.head))throw new HubError('管理仓库提交未核实。');
    previous=input.previous_report||null;
    clientFactory=entry=>{try{return new SnapshotClient(entry,input.books?.[entry.id]);}catch(e){return {snapshot:async()=>{throw e;}};}};
  }else{
    if(!o.management)throw new HubError('需要 --management 管理仓库地址。');management=parseRepository(o.management).url;
    const token=o.write?process.env.NOVEL_HUB_GITHUB_TOKEN||'':'';
    if(o.write&&!token)throw new HubError('缺少 NOVEL_HUB_GITHUB_TOKEN；未执行任何写入。');
    client=new GitHubClient(management,{token});source=await loadRegistry(client,o.branch||'');registry=source.registry;
    if(source.missing)throw new HubError('管理仓库尚未保存 books.json，请先在个人端保存清单。');
    previous=(await client.optionalJSON('reports/latest.json',source.head))?.data||null;
    clientFactory=entry=>new GitHubClient(entry.repository_url); // 小说读取不携带管理仓库凭证。
  }
  const report=preserveValidStates(await inspectRegistry(registry,{clientFactory}),previous);
  const runId=o['run-id']||globalThis.crypto.randomUUID().replaceAll('-','');
  const files=reportBundle(report,runId),bundle={type:'novel-hub-write-bundle-v1',management_repository:management,branch:source.branch,
    guard:{books_sha256:source.fileHash,registry_revision:registry.revision,initial_commit:source.head},files};
  if(o.output)await fs.writeFile(o.output,files['reports/latest.json']);
  if(o.bundle)await fs.writeFile(o.bundle,JSON.stringify(bundle,null,2)+'\n');
  let remote=null;
  if(o.write){
    const current=await loadRegistry(client,source.branch);
    if(current.fileHash!==source.fileHash)throw new HubError('检查期间名单改变，未写报告；重新读取后检查。','conflict');
    const latest=(await client.optionalJSON('reports/latest.json',current.head))?.data;
    if(latest&&Date.parse(latest.checked_at)>Date.parse(report.checked_at))throw new HubError('远端已有更新报告，未覆盖。','conflict');
    remote=await client.writeFiles(files,{expectedHead:current.head,branch:source.branch});
  }
  console.log(JSON.stringify({date:report.date,counts:report.counts,report_path:o.output||null,bundle_path:o.bundle||null,remote,
    results:report.results.map(({title,status,reason})=>({title,status,reason})),note:remote?'已原子写回并回读核对。':'尚未写入远端；输出文件或聊天回复不等于仓库已更新。'},null,2));
  return {report,bundle,remote};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))run(process.argv.slice(2)).catch(error=>{console.error(JSON.stringify({error:error.message,remote_completed:false}));process.exitCode=2;});
