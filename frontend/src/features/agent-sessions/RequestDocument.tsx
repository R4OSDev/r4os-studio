import {useEffect,useRef} from 'react';
import {EditorState} from '@codemirror/state';
import {EditorView} from '@codemirror/view';

/** Read-only viewport rendering keeps one scroll position for the whole body. */
export function RequestDocument({text}:{text:string}) {
  const parent=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    const view=new EditorView({parent:parent.current!,state:EditorState.create({doc:text,extensions:[
      EditorState.readOnly.of(true),EditorView.editable.of(false),EditorView.lineWrapping,
      EditorView.contentAttributes.of({'aria-label':'Full formatted request','aria-readonly':'true',tabindex:'0'}),
      EditorView.theme({
        '&':{height:'100%',backgroundColor:'#18111f',color:'#ddcbe8'},
        '.cm-scroller':{fontFamily:'ui-monospace,SFMono-Regular,Consolas,monospace',lineHeight:'1.65'},
        '.cm-content':{padding:'16px 0'},'.cm-line':{padding:'0 20px'},
        '&.cm-focused':{outline:'none'},'&.cm-focused .cm-content':{outline:'none'},
      },{dark:true}),
    ]})});
    return()=>view.destroy();
  },[text]);
  return <div ref={parent} className="request-original-content"/>;
}
