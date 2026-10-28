import {mergeQueryHistory} from './query-model.mjs';
// One ordered save at a time. Edits made during a request get their own latest
// snapshot; an ambiguous failure requires an explicit retry, never a loop.
export class AutoSync{
  constructor({snapshot,save,canSave=()=>true,onCommit=()=>{},onStatus=()=>{},delay=650,schedule=(fn,ms)=>setTimeout(fn,ms),cancel=id=>clearTimeout(id)}){Object.assign(this,{snapshot,save,canSave,onCommit,onStatus,delay,schedule,cancel});this.version=0;this.savedVersion=0;this.running=false;this.fault=null;this.timer=null;}
  get dirty(){return this.version!==this.savedVersion;}
  touch(){this.version++;this.cancel(this.timer);if(!this.running&&!this.fault){this.onStatus('waiting');this.timer=this.schedule(()=>this.flush(),this.delay);}return this.version;}
  async flush(){
    this.cancel(this.timer);if(this.running||this.fault||!this.dirty)return;
    this.running=true;
    try{while(this.dirty){
      if(!this.canSave()){this.onStatus('authorization_required');return;}
      const version=this.version,value=this.snapshot();this.onStatus('saving');
      let result;try{result=await this.save(value);}catch(error){this.fault=error;this.onStatus('error',error);return;}
      this.savedVersion=version;this.onCommit(result,version===this.version);
    }this.onStatus('saved');}finally{this.running=false;}
  }
  async retry(){this.fault=null;await this.flush();}
  acknowledge(){if(this.running)throw new Error('请等待当前同步结束。');this.cancel(this.timer);this.savedVersion=this.version;this.fault=null;}
}

// Keep existing local edits when first upgrading. Conflicting records are not
// silently replaced; the UI can ask the author to choose a version.
export function mergeRegistries(remote,local,base=null){
  const key=b=>b.repository_url.toLowerCase(),map=list=>new Map(list.map(b=>[key(b),b]));
  const r=map(remote.books),l=map(local.books),b=map(base?.books||[]),books=[],conflicts=[];
  const same=(x,y)=>JSON.stringify(x)===JSON.stringify(y);
  const meaningful=x=>x?Object.fromEntries(Object.entries(x).filter(([k])=>!['id','baseline'].includes(k))):x;
  for(const id of new Set([...r.keys(),...l.keys(),...b.keys()])){
    const rv=r.get(id),lv=l.get(id),bv=b.get(id);let value;
    if(base){if(same(lv,bv))value=rv;else if(same(rv,bv)||same(rv,lv))value=lv;else{conflicts.push({remote:rv,local:lv});value=rv;}}
    else if(!rv)value=lv;else if(!lv||same(meaningful(rv),meaningful(lv)))value=rv;else{conflicts.push({remote:rv,local:lv});value=rv;}
    if(value)books.push(value);
  }
  const rs=remote.settings||{},ls=local.settings||{},bs=base?.settings||{};
  let settings=rs;if(base){if(same(rs,bs))settings=ls;else if(!same(ls,bs)&&!same(ls,rs))conflicts.push({settings:true});}else if(!Object.keys(rs).length)settings=ls;else if(Object.keys(ls).length&&!same(ls,rs))conflicts.push({settings:true});
  const {settings:oldSettings,...rest}=remote;const history=mergeQueryHistory(remote.query_history||[],local.query_history||[]);return {registry:{...rest,books,...(Object.keys(settings).length?{settings}:{}),...(history.length?{query_history:history}:{})},conflicts};
}
