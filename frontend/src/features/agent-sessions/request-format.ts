/** Presentation only: retain number/string lexemes instead of reserializing JSON. */
export function formatRequest(original:string):{text:string;notice:string|null} {
  const source=original.charCodeAt(0)===0xfeff?original.slice(1):original;
  try{JSON.parse(source);}catch{return {text:original,notice:'This body is not valid JSON. The original text is shown.'};}
  const tokens=/"(?:\\.|[^"\\])*"|[{}[\],:]|[^\s{}[\],:"]+/g;
  const parts:string[]=[];let chunk='',size=0,depth=0;
  const append=(text:string)=>{
    size+=text.length;if(size>32*1024*1024)throw Error('Formatted view exceeds its display budget.');
    chunk+=text;if(chunk.length>=65536){parts.push(chunk);chunk='';}
  };
  const indent=()=> '  '.repeat(Math.min(depth,32));
  try{
    if(original.charCodeAt(0)===0xfeff)append('\ufeff');
    let current=tokens.exec(source),following=tokens.exec(source),previous='';
    while(current){
      const token=current[0],next=following?.[0];
      if(token==='{'||token==='['){
        append(token);depth++;
        if(next!=='}'&&next!==']')append('\n'+indent());
      }else if(token==='}'||token===']'){
        depth--;
        if(previous!=='{'&&previous!=='[')append('\n'+indent());
        append(token);
      }else if(token===',')append(',\n'+indent());
      else if(token===':')append(': ');
      else if(token.startsWith('"')&&next!==':'){
        // Consume escaped backslashes together, so literal \\n stays literal.
        // Real JSON line breaks become readable continuation lines in this view.
        append(token.replace(/\\(?:r\\n|n|r|["\\/bft]|u[0-9a-fA-F]{4})/g,
          escape=>escape==='\\n'||escape==='\\r'||escape==='\\r\\n'?'\n'+indent()+'  ':escape));
      }else append(token);
      previous=token;current=following;following=current?tokens.exec(source):null;
    }
    parts.push(chunk);return {text:parts.join(''),notice:null};
  }catch{return {text:original,notice:'Formatting exceeded its display budget. The complete original text is shown.'};}
}
