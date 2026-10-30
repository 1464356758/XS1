import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeSearch,matchesBook,filterBooks,pickBooks,filterChapters,bindSearch} from '../dist/search.mjs';
const books=Object.freeze([
 Object.freeze({id:'alpha',title:'雨夜书店',repository_url:'https://github.com/Example/Alpha-Book',enabled:true}),
 Object.freeze({id:'beta',title:'长安旧事',repository_url:'https://github.com/Other/Beta',enabled:false}),
 Object.freeze({id:'gamma',title:'雨夜来信',repository_url:'https://github.com/Example/Gamma',enabled:true})
]);
test('book search normalizes full width text case and whitespace across title and repository',()=>{
 assert.equal(normalizeSearch('　ＡＬＰＨＡ  书店　'),'alpha 书店');
 assert.deepEqual(filterBooks(books,'书店 EXAMPLE').map(x=>x.id),['alpha']);
 assert.equal(matchesBook(books[1],'ｂＥＴＡ'),true);
 assert.equal(filterBooks(books,' ').length,3);
});
test('search treats symbols as literal text and keeps original books order and enabled selection',()=>{
 const before=JSON.stringify(books);assert.deepEqual(filterBooks(books,'.*'),[]);assert.deepEqual(filterBooks(books,'<img>'),[]);
 assert.deepEqual(filterBooks(books,'雨夜').map(x=>x.id),['alpha','gamma']);assert.equal(JSON.stringify(books),before);assert.equal(books[1].enabled,false);
});
test('a filtered picker never silently selects another novel and clearing restores the retained selection',()=>{
 assert.equal(pickBooks(books,'beta','alpha').selectedId,'');
 assert.equal(pickBooks(books,'不存在','alpha').selectedId,'');
 assert.equal(pickBooks(books,'','alpha').selectedId,'alpha');
 assert.equal(pickBooks(books,'beta','beta').selectedId,'beta');
 assert.equal(pickBooks(books,'','removed').selectedId,'alpha');
 assert.equal(pickBooks([],'','alpha').selectedId,'');
});
test('one hundred synthetic books can be found by repository without changing the query scope',()=>{
 const many=Array.from({length:100},(_,i)=>({id:String(i),title:'合成书'+i,repository_url:'https://github.com/example/demo-'+String(i).padStart(3,'0'),enabled:i%2===0}));
 assert.deepEqual(filterBooks(many,'ＤＥＭＯ－０９７').map(x=>x.id),['97']);assert.equal(many.filter(x=>x.enabled).length,50);
});
const chapters=[{number:2,title:'第二封信'},{number:20,title:'雨夜书店'},{number:22,title:'雨夜归来'},{number:23,title:'长安归来'}];
test('chapter numbers match exactly including leading zeroes full width digits and 第章 notation',()=>{
 for(const query of ['22','０２２','第22章','第 022 章'])assert.deepEqual(filterChapters(chapters,query).map(x=>x.number),[22]);
 assert.deepEqual(filterChapters(chapters,'2').map(x=>x.number),[2]);assert.deepEqual(filterChapters(chapters,'0'),[]);assert.deepEqual(filterChapters(chapters,'999'),[]);
});
test('chapter titles and multiple keywords filter without changing the directory',()=>{
 const before=JSON.stringify(chapters);assert.deepEqual(filterChapters(chapters,'雨夜').map(x=>x.number),[20,22]);assert.deepEqual(filterChapters(chapters,'022 归来').map(x=>x.number),[22]);assert.equal(filterChapters(chapters,'').length,4);assert.equal(JSON.stringify(chapters),before);
});
class Input extends EventTarget{value='';hidden=false;focused=false;focus(){this.focused=true;}}
function event(type,properties={}){const e=new Event(type,{cancelable:true});for(const [key,value] of Object.entries(properties))Object.defineProperty(e,key,{value});return e;}
test('Chinese composition waits for the completed input and Escape or clear resets the same view',()=>{
 const input=new Input(),clear=new Input();let updates=0;bindSearch({input,clear,onChange:()=>updates++});assert.equal(clear.hidden,true);
 input.value='雨';input.dispatchEvent(event('input',{isComposing:true}));assert.equal(updates,0);
 input.dispatchEvent(event('compositionend'));assert.equal(updates,1);assert.equal(clear.hidden,false);
 const enter=event('keydown',{key:'Enter',isComposing:false});input.dispatchEvent(enter);assert.equal(enter.defaultPrevented,true);assert.equal(updates,1);
 input.dispatchEvent(event('keydown',{key:'Escape',isComposing:true}));assert.equal(input.value,'雨');
 input.dispatchEvent(event('keydown',{key:'Escape',isComposing:false}));assert.equal(input.value,'');assert.equal(clear.hidden,true);
 input.value='书店';input.dispatchEvent(event('input'));clear.dispatchEvent(event('click'));assert.equal(input.value,'');assert.equal(input.focused,true);
});
