import test from 'node:test';
import assert from 'node:assert/strict';
import {newBookPrompt,SYSTEM_REPOSITORY} from '../dist/hub-core.mjs';

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

test('new book prompt refuses template, management repository, invalid URL and oversized input',()=>{
  for(const repository of [SYSTEM_REPOSITORY,'https://github.com/example/manager','https://example.com/owner/repo'])assert.throws(()=>newBookPrompt({repository,management:'https://github.com/example/manager'}));
  assert.throws(()=>newBookPrompt({repository:'https://github.com/example/new',preferences:'字'.repeat(1201)}));
});
