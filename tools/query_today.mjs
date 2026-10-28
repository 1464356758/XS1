#!/usr/bin/env node
import fs from 'node:fs/promises';
import {GitHubClient,loadRegistry,saveRegistry} from '../web/dist/hub-core.mjs';
import {inspectTodayRegistry,rememberQuery} from '../web/dist/today-query.mjs';
const args=process.argv.slice(2);const option=name=>{const i=args.indexOf(name);return i<0?undefined:args[i+1];};
if(args.includes('--help')){console.log('查询已勾选小说今天是否更新：node tools/query_today.mjs --management https://github.com/owner/repo [--branch main] [--output result.json] [--write]\n按北京时间与最新章节文件提交日期判断，不使用计划时间或每日完成回执。只读无需凭证；--write使用环境中的NOVEL_HUB_GITHUB_TOKEN保存最近7天记录。');process.exit(0);}
try{
 const management=option('--management');if(!management)throw new Error('缺少 --management 管理仓库链接。');
 const client=new GitHubClient(management,{preferGit:true,token:process.env.NOVEL_HUB_GITHUB_TOKEN||''}),source=await loadRegistry(client,option('--branch')||'');
 const report=await inspectTodayRegistry(source.registry);let saved=null;
 if(args.includes('--write'))saved=await saveRegistry(client,rememberQuery(source.registry,report),{branch:source.branch,baseFileHash:source.fileHash});
 const result={...report,...(saved?{saved_commit:saved.commit}:{})},text=JSON.stringify(result,null,2)+'\n';
 if(option('--output'))await fs.writeFile(option('--output'),text);console.log(text);
}catch(error){console.error(error.message);process.exitCode=1;}
