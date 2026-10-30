#!/usr/bin/env python3
"""生成空的新书母版；绝不打包本书身份、进度或正文。"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def build(root=ROOT,out=None):
    root=Path(root).resolve();out=Path(out or root/'初始化系统包.zip').resolve()
    names=['AGENTS.md','README.md','启动新书.txt','每日一章指令.txt','docs/连载冻结与发布前检查.md','docs/写作与叙事检查.md','docs/专项技法.md','docs/每日自动更新.md','docs/旧书接入工作台.md','docs/管理端与代发端.md','docs/网页部署与首次使用.md','docs/工作台1.1交互与同步.md','docs/今日更新查询.md','docs/工作台1.3最终复查.md','docs/工作台搜索.md','docs/assets/novel-search-mobile-20261027.jpg','docs/assets/final-owner-mobile-20261027.jpg','执行规程.md','工具使用与数据格式.md','平台研究与选题.md','system_config.json','platforms.json','.gitignore','docs/线上同步协议.md','docs/正文直接读取.md','docs/私密稿保存.md','requirements-private.txt']
    files={name:(root/name).read_bytes() for name in names if not name.startswith('docs/assets/')}
    files['docs/旧章只读核验.md']=(root/'docs/旧章只读核验.md').read_bytes()
    files['docs/定时执行器.md']=(root/'docs/定时执行器.md').read_bytes()
    # Historical verification describes the original author's enrollment, not
    # the new project's state. Keep operational rules without old book records.
    for name, body in list(files.items()):
        if name.startswith('docs/') and name.endswith('.md'):
            text=body.decode('utf-8')
            text=re.sub(r'\n## 本次接入\n.*?(?=\n## |\Z)', '\n', text, flags=re.S)
            text=re.sub(r'\n## 对现有小说的直接读取\n.*?(?=\n## |\Z)', '\n', text, flags=re.S)
            text=re.sub(r'^.*\]\(assets/[^)]+\).*(?:\n|$)', '', text, flags=re.M)
            files[name]=text.encode('utf-8')
        elif name.startswith('docs/assets/'):
            del files[name]
    files['.github/workflows/novel-executor.yml']=(root/'.github/workflows/novel-executor.yml').read_bytes()
    files['.automation/config.json']=(json.dumps({'schema_version':1,'book_id':None,'automation_id':None},ensure_ascii=False,indent=2)+'\n').encode()
    for folder in ('tools','templates','tests'):
        for path in sorted((root/folder).glob('*')):
            if path.is_file() and path.suffix in ('.py','.mjs','.json','.md','.txt'):
                files[path.relative_to(root).as_posix()]=path.read_bytes()
    # 定时巡检工具与网页共用规则，离线包必须包含其实际依赖。
    for folder in ('web/dist','web/tests','web/server'):
        for path in sorted((root/folder).glob('*')):
            if path.is_file() and path.suffix in ('.html','.js','.mjs','.css','.svg','.webmanifest'):
                files[path.relative_to(root).as_posix()]=path.read_bytes()
    config=json.loads((root/'project_config.json').read_text())
    config['project_name']='新小说项目';config['authority']={'mode':'github','repository_url':'','branch':'main'}
    config['writing']['platform']=None;config['writing']['genre']=None
    config['storage']={'mode':'plain_files','requires_reader_key':False}
    files['project_config.json']=(json.dumps(config,ensure_ascii=False,indent=2)+'\n').encode()
    files['README.md']='''# 新小说初始化母版 V4.3\n\n本包是空系统，没有上一部小说的身份、进度、正文或选题。\n\n1. 将包内文件复制到新GitHub仓库根目录。\n2. 把新仓库链接与《启动新书.txt》发送给具备GitHub读写和代码执行能力的GPT。\n3. 先选择平台，再核查规则、榜单和5—10个原创选题，等作者选择。\n4. 新书默认采用即冻结，启用V4.3写作任务书、限信息审读与叙事证据检查。详见docs/写作与叙事检查.md。\n5. 之后使用《每日一章指令.txt》，一次只完成一章；到期全文回看在冻结前，发布回执单独登记。\n6. 网页读取正式进度；个人端可授权保存检查清单。定时任务须在GPT实际建立，不自动投稿。\n\n已有作品先核对实际状态，不用本包覆盖。升级代码不自动追认旧章通过新检查，也不解冻旧章。\n'''.encode()
    files['book/README.md']='# 空工作区\n\n由GPT运行bootstrap生成这本书的新身份。正文与记录直接保存，无需阅读密钥。不要复制旧书state.json。\n'.encode()
    files['research/README.md']='# 尚未研究\n\n选定平台后重新核查官方规则和榜单。\n'.encode()
    empty={'schema_version':1,'system_version':config['system_version'],'initialized':False,'book':{'id':None,'title':'新小说（待初始化）','platform':None,'selected_topic_id':None},'source':{'repository_url':None,'branch':'main','generated_at':None,'state_revision':0,'workflow_revision':0},'progress':{'target_chapters':100,'adopted_chapters':0,'target_han':900000,'actual_han':0,'completed':False,'needs_revalidation':[]},'task':{'phase':'NOT_INITIALIZED','label':'等待初始化','chapter':1,'detail':'复制启动指令交给GPT，建立这本书的新身份。','next_action':'读取启动新书.txt，填入新仓库链接后bootstrap。','updated_at':None},'chapters':[],'topics':[],'research':None,'history':[]}
    files['online/index.json']=(json.dumps(empty,ensure_ascii=False,indent=2)+'\n').encode()
    if (root/'.github/workflows/validate.yml').exists():files['.github/workflows/validate.yml']=(root/'.github/workflows/validate.yml').read_bytes()
    assert not any(name.startswith(('book/chapters/','book/records/','book/candidates/')) or name in ('book/state.json','book/workflow.json') for name in files)
    manifest={'template_version':config['system_version'],'workspace_version':config['workspace_version'],'contains_novel_data':False,'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
    files['INIT_MANIFEST.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()):
            entry=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            entry.compress_type=zipfile.ZIP_DEFLATED
            entry.external_attr=0o100644<<16
            archive.writestr(entry,data)
    with zipfile.ZipFile(out) as archive:
        assert archive.testzip() is None
        for name,sha in manifest['files'].items():assert hashlib.sha256(archive.read(name)).hexdigest()==sha
    return {'path':str(out),'files':len(files),'contains_novel_data':False,'bytes':out.stat().st_size}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out');args=p.parse_args();print(json.dumps(build(out=args.out),ensure_ascii=False,indent=2))
