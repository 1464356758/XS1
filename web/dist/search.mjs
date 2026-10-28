// Local display filters only; they never change registry selection or fetch data.
export const normalizeSearch=value=>String(value??'').normalize('NFKC').toLocaleLowerCase('zh-CN').trim().replace(/\s+/gu,' ');
const terms=query=>normalizeSearch(query).split(' ').filter(Boolean);
export function matchesBook(book,query){
  const text=normalizeSearch([book.title,book.repository_url].filter(Boolean).join(' '));
  return terms(query).every(term=>text.includes(term));
}
export const filterBooks=(books,query)=>books.filter(book=>matchesBook(book,query));
export function pickBooks(books,query,chosen=''){
  const matches=filterBooks(books,query);
  const selected=matches.find(book=>book.id===chosen)||(!normalizeSearch(query)&&!books.some(book=>book.id===chosen)?matches[0]:null);
  return {matches,selectedId:selected?.id||''};
}
function chapterNumber(query){
  const match=/^(?:第\s*)?(\d+)(?:\s*章)?$/u.exec(query);
  return match&&Number.isSafeInteger(Number(match[1]))?Number(match[1]):null;
}
export function filterChapters(chapters,query){
  const normalized=normalizeSearch(query),number=chapterNumber(normalized);
  if(number!==null)return chapters.filter(chapter=>chapter.number===number);
  const words=terms(query);
  return chapters.filter(chapter=>words.every(word=>{const n=chapterNumber(word);return n!==null?chapter.number===n:normalizeSearch(chapter.title).includes(word);}));
}
export function bindSearch({input,clear,onChange}){
  const update=()=>{clear.hidden=!input.value;onChange();};
  input.addEventListener('input',event=>{if(!event.isComposing)update();});
  input.addEventListener('compositionend',update);
  input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.isComposing)event.preventDefault();if(event.key==='Escape'&&!event.isComposing){event.preventDefault();input.value='';update();}});
  clear.addEventListener('click',()=>{input.value='';update();input.focus();});
  clear.hidden=!input.value;
}
