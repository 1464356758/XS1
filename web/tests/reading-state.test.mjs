import test from 'node:test';
import assert from 'node:assert/strict';
import {progressKey,readingChapter,copiedChapter,captureChapter,ExportJob,publicationStatus} from '../dist/reading-state.mjs';
const chapters=[{number:1,title:'合成一',sha256:'a'},{number:2,title:'合成二',sha256:'b'},{number:3,title:'合成三',sha256:'c'}];
test('reading resumes its last verified chapter and falls back safely when removed',()=>{
 assert.equal(readingChapter(chapters,{chapter:2}).number,2);
 assert.equal(readingChapter(chapters,{chapter:9}).number,1);
 assert.equal(readingChapter([],null),null);
 assert.equal(readingChapter(chapters,{chapter:'2'}).number,1);
});
test('copy progress advances only if its exact copied version is still current',()=>{
 assert.equal(copiedChapter(chapters,{chapter:2,sha256:'b'}).number,3);
 assert.equal(copiedChapter(chapters,{chapter:2,sha256:'old'}).number,2);
 assert.equal(copiedChapter(chapters,{chapter:3,sha256:'c'}).number,3);
 assert.equal(copiedChapter([],null),null);
});
test('local convenience progress is isolated by repository branch and novel identity',()=>{
 const k=progressKey('Example/Book','main','bookA');
 assert.equal(k,progressKey('example/book','main','bookA'));
 for(const args of [['example/other','main','bookA'],['example/book','draft','bookA'],['example/book','main','bookB']])assert.notEqual(k,progressKey(...args));
 assert.notEqual(k,progressKey('example/book','main','bookA','copied'));
});
test('clipboard completion records the captured chapter even if selection changes while awaiting',async()=>{
 const book={chapter:chapters[0],text:'合成一正文'},copy=captureChapter(book,book.chapter,book.text);
 let done;const clipboard=new Promise(resolve=>{done=resolve;});
 const saved=clipboard.then(()=>({chapter:copy.chapter,sha256:copy.sha256,text:copy.text}));
 book.chapter=chapters[1];book.text='合成二正文';done();
 assert.deepEqual(await saved,{chapter:1,sha256:'a',text:'合成一正文'});
 assert.equal(Object.isFrozen(copy),true);
});
test('whole book export rejects duplicate start and an old job cannot finish a new job',()=>{
 const manager=new ExportJob(),a={},b={},first=manager.start(a);
 assert.throws(()=>manager.start(a));
 const second=manager.start(b);assert.equal(manager.current(first),false);assert.equal(first.cancelled,true);
 manager.finish(first);assert.equal(manager.current(second),true);
 manager.cancel();assert.equal(manager.current(second),false);
});

test('platform publication is read from an exact matching receipt and absence is not called unpublished',()=>{
 const chapter=chapters[0];assert.match(publicationStatus(null,chapter),/尚未登记/);
 const state={serialization:{published:{'1':{text_sha256:'a',published_at:'2026-10-27T02:00:00Z',evidence:'明确合成测试依据'}}}};
 assert.match(publicationStatus(state,chapter),/仓库已登记/);assert.match(publicationStatus(state,chapter),/实际平台状态仍以发布页面为准/);
 state.serialization.published['1'].text_sha256='old';assert.match(publicationStatus(state,chapter),/不符/);
 state.serialization.published['1']={text_sha256:'a',published_at:'2026-10-27'};assert.match(publicationStatus(state,chapter),/不符/);
});
