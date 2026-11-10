import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PLATFORMS,PLATFORM_HEAT,platformChoices,matchesPlatform} from '../dist/platform-catalog.mjs';
import {newBookPrompt} from '../dist/hub-core.mjs';

test('all 42 attachment entries plus existing Dianzhong are available in the init catalog',async()=>{
  const catalog=JSON.parse(await readFile(new URL('../../platforms.json',import.meta.url),'utf8'));
  assert.equal(PLATFORMS.length,43);
  assert.equal(new Set(PLATFORMS.map(p=>p.id)).size,43);
  assert.equal(new Set(PLATFORMS.map(p=>p.name)).size,43);
  assert.equal(catalog.platforms.length,43);
  for(const p of PLATFORMS){
    const entry=catalog.platforms.find(e=>e.id===p.id);
    assert.equal(entry?.display_name,p.name);
    assert.equal(entry.writer_url,p.writer_url);
    assert.ok(p.writer_url.startsWith('https://'));
  }
  for(const id of ['qidian','fanqie','qimao','jinjiang','dianzhong','qimiao','qidian_female','qimao_short','kuaidian'])assert.ok(PLATFORMS.some(p=>p.id===id),id);
});

test('dated heat ranking uses one metric and leaves channels unranked',()=>{
  assert.equal(PLATFORM_HEAT.month,'2026-02');
  assert.ok(PLATFORM_HEAT.url.startsWith('https://www.questmobile.com.cn/'));
  const ranked=platformChoices().matches.filter(p=>p.heat);
  assert.deepEqual(ranked.map(p=>[p.id,p.heat.rank,p.heat.mau_wan]),[
    ['fanqie',1,25988],['qimao',2,8610],['zhangyue',3,4090],['qqread',4,2680],['qidian',5,1936],['shuqi',6,1920]
  ]);
  for(const id of ['fanqie_short','qimao_short','qimiao','qidian_female','jinjiang'])assert.equal(PLATFORMS.find(p=>p.id===id).heat,null);
  assert.equal(platformChoices().matches.slice(0,6).filter(p=>p.heat).length,6);
});

test('platform search supports aliases, full width text, case, and multiple topic terms',()=>{
  for(const [query,id] of [['ＳＦ','sfacg'],['菠萝包','sfacg'],['１７Ｋ','17k'],['QQREAD','qqread'],['  花语  女频 ','zongheng_female'],['盐言','zhihu'],['板栗','zhangyue'],['次元姬','ciyuanji']]){
    assert.ok(platformChoices(query).matches.some(p=>p.id===id),query);
  }
  assert.ok(platformChoices('短篇').matches.length>3);
  assert.ok(platformChoices('女频').matches.length>8);
  assert.deepEqual(platformChoices('确实不存在的平台').matches,[]);
});

test('filtering, no results and sort changes preserve the exact chosen platform without auto-selection',()=>{
  const chosen=PLATFORMS.find(p=>p.id==='qimao').name;
  const filtered=platformChoices('菠萝包',chosen);
  assert.equal(filtered.selected.name,chosen);
  assert.equal(filtered.retained.name,chosen);
  assert.ok(filtered.matches.every(p=>p.name!==chosen));
  assert.equal(platformChoices('无结果xyz',chosen).selected.name,chosen);
  assert.equal(platformChoices('',chosen,'name').selected.name,chosen);
  assert.equal(platformChoices('',chosen).retained,null);
  assert.equal(platformChoices('七猫').selected,null);
  assert.equal(platformChoices('','不存在的旧选项').selected,null);
  const names=platformChoices('','', 'name').matches.map(p=>p.name);
  assert.ok(names.every((name,i)=>i===0||names[i-1].localeCompare(name,'zh-CN')<=0));
});

test('every selected platform reaches the generated prompt unchanged and still requires current research',()=>{
  for(const p of PLATFORMS){
    const prompt=newBookPrompt({repository:'https://github.com/example/new-novel',platform:p.name});
    assert.ok(prompt.includes('【平台】'+p.name));
    assert.ok(prompt.includes('核查现行官方创作'));
    assert.ok(prompt.includes('我已指定平台就直接研究，不重复问'));
  }
  assert.ok(matchesPlatform(PLATFORMS.find(p=>p.id==='sfacg'),'ｓｆ'));
});
