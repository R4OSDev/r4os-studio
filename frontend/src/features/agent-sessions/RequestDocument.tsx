import {useEffect,useRef} from 'react';
import {countColumn,EditorState,RangeSetBuilder} from '@codemirror/state';
import {Decoration,EditorView,ViewPlugin} from '@codemirror/view';
import type {DecorationSet,ViewUpdate} from '@codemirror/view';

function wrapIndents(view:EditorView):DecorationSet {
  const ranges=new RangeSetBuilder<Decoration>();let previous=-1;
  for(const {from,to} of view.visibleRanges){
    for(let position=from;position<=to;){
      const line=view.state.doc.lineAt(position);
      if(line.from>previous){
        previous=line.from;
        const prefix=view.state.sliceDoc(line.from,Math.min(line.to,line.from+128)).match(/^[ \t]+/)?.[0];
        if(prefix){
          const columns=countColumn(prefix,view.state.tabSize);
          ranges.add(line.from,line.from,Decoration.line({attributes:{
            style:`--request-wrap-indent:min(${columns}ch,25vw,160px)`,
          }}));
        }
      }
      position=line.to+1;
    }
  }
  return ranges.finish();
}

const alignedWrapping=ViewPlugin.fromClass(class {
  decorations:DecorationSet;
  constructor(view:EditorView){this.decorations=wrapIndents(view);}
  update(update:ViewUpdate){
    if(update.docChanged||update.viewportChanged)this.decorations=wrapIndents(update.view);
  }
},{decorations:plugin=>plugin.decorations});

/** Read-only viewport rendering keeps one scroll position for the whole body. */
export function RequestDocument({text}:{text:string}) {
  const parent=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    const view=new EditorView({parent:parent.current!,state:EditorState.create({doc:text,extensions:[
      EditorState.readOnly.of(true),EditorView.editable.of(false),EditorView.lineWrapping,alignedWrapping,
      EditorView.contentAttributes.of({'aria-label':'Full formatted request','aria-readonly':'true',tabindex:'0'}),
      EditorView.theme({
        '&':{height:'100%',backgroundColor:'#18111f',color:'#ddcbe8'},
        '.cm-scroller':{fontFamily:'ui-monospace,SFMono-Regular,Consolas,monospace',lineHeight:'1.65'},
        '.cm-content':{padding:'16px 0','--request-line-padding':'20px'},
        // Keep existing leading whitespace on the first line; wrapped lines
        // start at the same column without inserting characters into the text.
        '.cm-line':{padding:'0 var(--request-line-padding)',
          paddingLeft:'calc(var(--request-line-padding) + var(--request-wrap-indent,0px))',
          textIndent:'calc(0px - var(--request-wrap-indent,0px))'},
        '&.cm-focused':{outline:'none'},'&.cm-focused .cm-content':{outline:'none'},
      },{dark:true}),
    ]})});
    return()=>view.destroy();
  },[text]);
  return <div ref={parent} className="request-original-content"/>;
}
