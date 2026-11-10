import test from 'node:test';
import assert from 'node:assert/strict';
import {newBookPrompt,SYSTEM_REPOSITORY,TEMPLATE_REPOSITORY,REFERENCE_LIBRARY} from '../dist/hub-core.mjs';

test('new book prompt binds one new repository and waits for platform and topic choices',()=>{
  const prompt=newBookPrompt({repository:'https://github.com/example/new-novel.git'});
  assert.ok(prompt.includes('【唯一新书仓库】https://github.com/example/new-novel'));
  for(const required of ['先让我选择','INIT_MANIFEST.json','实际默认分支','不重新bootstrap','expected_sha','force=false','validate-index','WAITING_TOPIC','前面全部采用章只读','仅在我明确要求','same_context_approximation']){
    assert.ok(prompt.includes(required),required);
  }
});

test('new book prompt preserves selected platform and quotes optional preferences as data',()=>{
  const prompt=newBookPrompt({repository:'https://github.com/example/new-novel',platform:'七猫',preferences:'女频古言\n经商',management:'https://github.com/example/manager'});
  assert.ok(prompt.includes('【平台】七猫'));
  assert.ok(prompt.includes('【作者偏好】"女频古言\\n经商"'));
  assert.ok(prompt.includes('当前管理仓库 https://github.com/example/manager'));
});

test('new book and daily prompts carry the real library through the existing brief and release',async()=>{
  const {readFileSync}=await import('node:fs');
  const prompt=newBookPrompt({repository:'https://github.com/example/new-novel'});
  for(const value of [REFERENCE_LIBRARY,'reference_library/XS-KU.json','brief-request --references','narrative_review.reference_use'])assert.ok(prompt.includes(value),value);
  const source=readFileSync(new URL('../dist/hub-core.mjs',import.meta.url),'utf8');
  assert.match(source,/四、完成正文和实质审核\n[\s\S]*?如果本书已绑定reference_library/);
});

test('new book prompt uses 6000 characters from chapter one and requires the first-five review',()=>{
  const prompt=newBookPrompt({repository:'https://github.com/example/new-novel'});
  for(const value of ['150章','6000汉字','5500—6500','docs/前五章投稿验收.md','两部独立开篇','第3和第5章'])assert.ok(prompt.includes(value),value);
  assert.ok(!prompt.includes('默认100章'));
});

test('new book prompt refuses template, management repository, invalid URL and oversized input',()=>{
  for(const repository of [SYSTEM_REPOSITORY,TEMPLATE_REPOSITORY,REFERENCE_LIBRARY,'https://github.com/1464356758/XIAOSHUOV5.git','https://github.com/example/manager','https://example.com/owner/repo'])assert.throws(()=>newBookPrompt({repository,management:'https://github.com/example/manager'}));
  assert.throws(()=>newBookPrompt({repository:'https://github.com/example/new',preferences:'字'.repeat(1201)}));
});

test('new book prompt identifies the real template and matching downloadable package',()=>{
  const prompt=newBookPrompt({repository:'https://github.com/example/new-novel'});
  for(const value of [`【系统母版】${TEMPLATE_REPOSITORY}`,'patch_version为4.6.3','workspace_version为1.4.9','不混用旧包'])assert.ok(prompt.includes(value),value);
});
