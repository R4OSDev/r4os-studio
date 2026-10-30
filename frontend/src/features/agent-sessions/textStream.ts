/** Presentation only. Original React leaf values stay authoritative. */
type Leaf={element:HTMLElement;node:Text;value:string};
export class TextStream {
  private leaves=new Map<HTMLElement,Leaf>();private ordered:Leaf[]=[];
  private root:HTMLElement|null=null;private full='';private raw='';private visible=0;
  private ends:number[]=[0];private frame=0;private previous=0;private started=0;private wrote=0;
  private range:Range|null=null;private highlight:Highlight|null=null;
  bind(element:HTMLElement,value:string) {
    const node=element.firstChild;
    if(node?.nodeType===Node.TEXT_NODE)this.leaves.set(element,{element,node:node as Text,value});
  }
  unbind(element:HTMLElement){this.leaves.delete(element);}
  seed(raw:string,semantic:string){this.raw=raw;this.full=semantic;this.visible=semantic.length;}
  private clearGlow(){if(this.highlight&&CSS.highlights?.get('studio-stream-edge')===this.highlight)CSS.highlights.delete('studio-stream-edge');this.range=null;this.highlight=null;}
  finish(){
    cancelAnimationFrame(this.frame);this.frame=0;
    for(const leaf of this.ordered)if(leaf.node.data!==leaf.value)leaf.node.data=leaf.value;
    this.visible=this.full.length;this.clearGlow();
  }
  dispose(){this.finish();this.leaves.clear();this.ordered=[];this.root=null;}
  configure(root:HTMLElement,raw:string,active:boolean) {
    this.root=root;
    this.ordered=Array.from(root.querySelectorAll<HTMLElement>('[data-stream-leaf]')).map(e=>this.leaves.get(e)).filter((v):v is Leaf=>!!v);
    const full=this.ordered.map(v=>v.value).join(''),previous=this.full,wasCaughtUp=this.visible>=previous.length;
    const changed=full!==previous;
    const supported=typeof Intl.Segmenter==='function'&&typeof Highlight==='function'&&typeof CSS!=='undefined'&&!!CSS.highlights&&CSS.supports('selector(::highlight(studio-stream-edge))');
    this.full=full;
    if(!active||!supported||document.hidden||matchMedia('(prefers-reduced-motion: reduce)').matches
      ||this.ordered.length>128||raw.length>8192||!raw.startsWith(this.raw)||!full.startsWith(previous)
      ||!!document.getSelection()&&!document.getSelection()!.isCollapsed){this.raw=raw;this.finish();return;}
    this.raw=raw;
    if(!changed)return;
    const segmenter=new Intl.Segmenter(undefined,{granularity:'grapheme'});
    this.ends=[0,...Array.from(segmenter.segment(full),v=>v.index+v.segment.length)];
    // A newly arrived combining/ZWJ suffix extends the already shown cluster
    // atomically, instead of exposing an interior Unicode boundary.
    this.visible=this.ends.find(value=>value>=this.visible)??full.length;
    const pending=this.ends.filter(value=>value>this.visible).length;
    if(pending>400){this.finish();return;}
    const now=performance.now();if(wasCaughtUp)this.started=now;if(!this.frame){this.started=now;this.previous=now;}
    this.render();
    if(!this.frame)this.frame=requestAnimationFrame(time=>this.tick(time));
  }
  private render(){
    let offset=0;
    for(const leaf of this.ordered){const value=leaf.value.slice(0,Math.max(0,this.visible-offset));if(leaf.node.data!==value)leaf.node.data=value;offset+=leaf.value.length;}
  }
  private point(offset:number):[Text,number]|null {
    for(const leaf of this.ordered){if(offset<=leaf.value.length)return[leaf.node,Math.min(offset,leaf.node.length)];offset-=leaf.value.length;}
    const leaf=this.ordered.at(-1);return leaf?[leaf.node,leaf.node.length]:null;
  }
  private glow(now:number){
    const index=this.ends.indexOf(this.visible),start=this.point(this.ends[Math.max(0,index-4)]??0),end=this.point(this.visible);
    if(!start||!end||!this.root)return;
    this.range??=new Range();this.range.setStart(...start);this.range.setEnd(...end);
    this.highlight??=new Highlight(this.range);CSS.highlights.set('studio-stream-edge',this.highlight);
    const fade=Math.min(1,Math.max(0,(now-this.wrote)/140));
    const color=[238,205,255].map((v,i)=>Math.round(v+([224,215,232][i]-v)*fade));
    this.root.style.setProperty('--studio-stream-edge-color',`rgb(${color.join(',')})`);
    this.root.style.setProperty('--studio-stream-edge-shadow',`rgba(181,120,232,${.45*(1-fade)})`);
  }
  private tick(now:number){
    this.frame=0;
    if(!this.root?.isConnected||!this.root.getClientRects().length||document.hidden
      ||matchMedia('(prefers-reduced-motion: reduce)').matches||!document.getSelection()?.isCollapsed){this.finish();return;}
    if(this.visible<this.full.length){
      if(now-this.started>480){this.finish();return;}
      const index=this.ends.indexOf(this.visible),pending=this.ends.length-1-index;
      const step=Math.min(64,Math.max(1,Math.floor((now-this.previous)*Math.min(900,90+pending*4)/1000)));
      this.visible=this.ends[Math.min(this.ends.length-1,index+step)];this.wrote=now;this.render();
    }
    this.previous=now;
    if(now-this.wrote<140){this.glow(now);this.frame=requestAnimationFrame(time=>this.tick(time));}
    else this.clearGlow();
  }
}
