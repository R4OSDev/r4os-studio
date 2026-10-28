// Studio companion: bounded project RGBA32/bitmap-ICO consumption, matched SDK.
use r4os::{App,abi,c_facades as c};
use core::{ffi::CStr,mem};
pub fn read(app:&App<'_>,kind:u32,index:u32,name:&CStr,out:&mut [u8])->Option<usize>{
 if out.len()>u32::MAX as usize{return None;}
 let mut facade:c::R4App=unsafe{mem::zeroed()};
 if unsafe{c::R4SdkAppFacade(app.start_context(),&mut facade)}!=0{return None;}
 let table=unsafe{facade.system.table.as_ref()}?;
 let offset=mem::offset_of!(c::R4XStartR4Sys,module_resource_read);
 if (table.size as usize)<offset+mem::size_of::<usize>() || table.module_resource_read==0{return None;}
 let mut path=[0u8;132];let mut resources=c::R4Resources{app:&mut facade};
 if unsafe{c::r4_resources_program_module_path(&mut resources,path.as_mut_ptr(),128)}<=0{return None;}
 let function:abi::R4SysFns::module_resource_read=unsafe{mem::transmute(table.module_resource_read as usize)};
 let count=unsafe{function(path.as_ptr(),kind,index,name.as_ptr().cast(),out.as_mut_ptr(),out.len() as u32)};
 if count<=0 || count as usize>out.len(){None}else{Some(count as usize)}
}
fn rgb(r:u8,g:u8,b:u8,a:u8,bg:u32)->u32 {
 let a=a as u32;let inv=255-a;
 (((r as u32*a+((bg>>16)&255)*inv+127)/255)<<16)|(((g as u32*a+((bg>>8)&255)*inv+127)/255)<<8)|((b as u32*a+(bg&255)*inv+127)/255)
}
pub fn rgba(bytes:&[u8],width:usize,height:usize,stride:usize,out:&mut [u32],bg:u32)->bool {
 if width==0 || height==0 || width>4096 || height>4096 || width*height>16_000_000 || stride!=width*4 || bytes.len()!=stride*height || out.len()<width*height{return false;}
 for (i,p) in bytes.chunks_exact(4).enumerate(){out[i]=rgb(p[0],p[1],p[2],p[3],bg);}true
}
fn u16le(p:&[u8],at:usize)->Option<u16>{Some(u16::from_le_bytes(p.get(at..at+2)?.try_into().ok()?))}
fn u32le(p:&[u8],at:usize)->Option<u32>{Some(u32::from_le_bytes(p.get(at..at+4)?.try_into().ok()?))}
pub fn icon(bytes:&[u8],preferred:usize,out:&mut [u32],bg:u32)->Option<(usize,usize)>{
 if u16le(bytes,0)?!=0 || u16le(bytes,2)?!=1{return None;}
 let count=u16le(bytes,4)? as usize;if count==0 || count>32 || bytes.len()<6+count*16{return None;}
 for i in 0..count{
  let at=6+i*16;let w=if bytes[at]==0{256}else{bytes[at] as usize};let h=if bytes[at+1]==0{256}else{bytes[at+1] as usize};
  if w!=preferred || h!=preferred{continue;}
  let offset=u32le(bytes,at+12)? as usize;let size=u32le(bytes,at+8)? as usize;let dib=bytes.get(offset..offset.checked_add(size)?)?;
  if out.len()<w*h || u32le(dib,0)?!=40 || u32le(dib,4)? as usize!=w || u32le(dib,8)? as usize!=h*2 || u16le(dib,12)?!=1 || u16le(dib,14)?!=32 || u32le(dib,16)?!=0 || dib.len()<40+w*h*4{return None;}
  for y in 0..h{for x in 0..w{let p=&dib[40+((h-1-y)*w+x)*4..][..4];out[y*w+x]=rgb(p[2],p[1],p[0],p[3],bg);}}
  return Some((w,h));
 }None
}
pub fn draw(paint:&mut r4os::gui::Paint<'_, '_, '_>,x:i32,y:i32,width:u32,height:u32,pixels:&[u32],scratch:&mut [u32])->bool {
 if width==0 || height==0 || width>4096 || height>4096 || pixels.len()<(width as usize)*(height as usize){return false;}
 let max_w=128u32.min(abi::gui_raster_max_width);if max_w==0{return false;}
 let max_h=128u32.min(abi::gui_raster_max_height).min(abi::gui_raster_max_pixels/max_w);if max_h==0{return false;}
 let mut top=0;while top<height{let mut left=0;while left<width{
  let w=(width-left).min(max_w);let h=(height-top).min(max_h);if scratch.len()<(w*h) as usize{return false;}
  for row in 0..h{let from=((top+row)*width+left) as usize;let to=(row*w) as usize;scratch[to..to+w as usize].copy_from_slice(&pixels[from..from+w as usize]);}
  let Some(px)=x.checked_add(left as i32)else{return false;};let Some(py)=y.checked_add(top as i32)else{return false;};
  if paint.raster(px,py,w,h,1,&scratch[..(w*h) as usize]).is_err(){return false;}left+=max_w;
 }top+=max_h;}true
}
