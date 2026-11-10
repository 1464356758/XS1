import {PLATFORMS,PLATFORM_HEAT,platformChoices,platformOptionLabel} from './platform-catalog.mjs';
import {bindSearch} from './search.mjs';
import {el} from './ui.mjs';

export function mountPlatformPicker({input,clear,sort,select,status,empty,detail,source,onChange}){
  let chosen=select.value;
  const addOption=(parent,p,label=platformOptionLabel(p))=>{const option=el('option',null,label);option.value=p.name;parent.append(option);};
  function render(){
    const {matches,selected,retained}=platformChoices(input.value,chosen,sort.value);
    select.replaceChildren();
    const blank=el('option',null,'还没决定，先让我选平台');blank.value='';select.append(blank);
    if(retained){const group=el('optgroup');group.label='当前选择（不在搜索结果中）';addOption(group,retained);select.append(group);}
    if(sort.value==='heat'){
      for(const [ranked,label] of [[true,'热度参考 · 已核实月活'],[false,'暂无可比热度 · 按名称排列']]){
        const group=el('optgroup');group.label=label;
        for(const p of matches.filter(p=>!!p.heat===ranked))addOption(group,p);
        if(group.children.length)select.append(group);
      }
    }else for(const p of matches)addOption(select,p);
    select.value=selected?.name||'';
    status.textContent='显示 '+matches.length+' / '+PLATFORMS.length+' 个入口'+(retained?' · 已保留所选平台':'');
    empty.hidden=matches.length>0;
    detail.replaceChildren();
    if(selected){
      const line=selected.heat?'热度参考第 '+selected.heat.rank+' · '+selected.heat.app+' 月活 '+selected.heat.mau_wan.toLocaleString('zh-CN')+' 万（'+PLATFORM_HEAT.month+'）':'暂无同口径热度数据，未排名';
      detail.append(el('strong',null,'已选：'+selected.name),el('p',null,selected.type+' · '+line));
      const link=el('a','text-link',selected.entry_note?'查看附件提供的入口 ↗':'作者 / 投稿入口 ↗');link.href=selected.writer_url;link.target='_blank';link.rel='noopener noreferrer';detail.append(link);
      if(selected.entry_note)detail.append(el('p','field-help',selected.entry_note));
    }else detail.append(el('p',null,'可以先留空。选定后，GPT 会核查该平台现行规则并研究选题。'));
    onChange();
  }
  source.replaceChildren(el('p',null,'按本目录中有同口径数据的 6 个阅读 App 月活排序。数据月份 '+PLATFORM_HEAT.month+'，核查于 '+PLATFORM_HEAT.checked_at+'，仅作流量参考。频道与专项入口不套用母站名次；其余入口暂无可比数据。'));
  const list=el('ol','platform-ranks');
  for(const p of PLATFORMS.filter(p=>p.heat).sort((a,b)=>a.heat.rank-b.heat.rank))list.append(el('li',null,p.heat.app+' · '+p.heat.mau_wan.toLocaleString('zh-CN')+' 万'));
  const link=el('a','text-link','查看 QuestMobile 报告 ↗');link.href=PLATFORM_HEAT.url;link.target='_blank';link.rel='noopener noreferrer';
  const table=el('a','text-link','数据表（第 5 页）↗');table.href=PLATFORM_HEAT.table_url;table.target='_blank';table.rel='noopener noreferrer';
  source.append(list,link,document.createTextNode(' · '),table,el('p','field-help','目录来自 2026-10-24 平台对照的 42 条入口，并保留试投方案中的点众，共 43 条；包含同品牌频道。热度不代表签约难度、收入或接受 AI 稿件，投稿前须核查最新规则。'));
  bindSearch({input,clear,onChange:render});
  sort.addEventListener('change',render);
  select.addEventListener('change',()=>{chosen=select.value;render();});
  render();
}
