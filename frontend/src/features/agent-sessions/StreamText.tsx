import {createContext,useContext,useLayoutEffect,useRef} from 'react';
import type {TextStream} from './textStream';
export const StreamContext=createContext<{engine:TextStream;enabled:boolean}|null>(null);
export function StreamLeaf({text}:{text:string}) {
  const context=useContext(StreamContext),element=useRef<HTMLSpanElement>(null);
  useLayoutEffect(()=>{const target=element.current;if(!target||!context?.enabled)return;context.engine.bind(target,text);return()=>context.engine.unbind(target);});
  return context?.enabled?<span ref={element} data-stream-leaf="">{text}</span>:text;
}
type Ast={type:string;tagName?:string;value?:string;properties?:Record<string,unknown>;children?:Ast[]};
export function streamTextPlugin(){
  return(tree:Ast)=>{
    const visit=(node:Ast)=>{
      if(!node.children||node.tagName==='pre'||node.tagName==='code')return;
      node.children=node.children.map(child=>{
        if(child.type==='text'&&typeof child.value==='string'){
          return {type:'element',tagName:'span',properties:{'data-studio-stream':'1'},children:[child]};
        }
        visit(child);return child;
      });
    };visit(tree);
  };
}
