// Studio companion: copy into the app. Uses the project's pinned SDK, not a new SDK.
const std=@import("std");
const r4os=@import("r4os");
pub fn own(ctx:*const r4os.r4sys.Context,kind:u32,index:u32,name:[:0]const u8,out:[]u8) ?[]const u8 {
 var path:[132]u8=.{0}**132;
 if(ctx.programModulePath(path[0..128])<=0)return null;
 const read=ctx.moduleResourceRead(@ptrCast(&path),kind,index,name.ptr,out);
 if(read<=0 or @as(usize,@intCast(read))>out.len)return null;
 return out[0..@intCast(read)];
}
fn flatten(r:u8,g:u8,b:u8,a:u8,bg:u32) u32 {
 const alpha:@TypeOf(bg)=a;const inv=255-alpha;
 const red=(@as(u32,r)*alpha+((bg>>16)&255)*inv+127)/255;
 const green=(@as(u32,g)*alpha+((bg>>8)&255)*inv+127)/255;
 const blue=(@as(u32,b)*alpha+(bg&255)*inv+127)/255;
 return (red<<16)|(green<<8)|blue;
}
pub fn rgba(bytes:[]const u8,width:usize,height:usize,stride:usize,out:[]u32,bg:u32) bool {
 if(width==0 or height==0 or width>4096 or height>4096 or width*height>16_000_000 or stride!=width*4 or bytes.len!=stride*height or out.len<width*height)return false;
 for(0..width*height)|i|{const p=bytes[i*4..][0..4];out[i]=flatten(p[0],p[1],p[2],p[3],bg);}
 return true;
}
pub fn icon(bytes:[]const u8,preferred:u16,out:[]u32,bg:u32) ?struct{width:u32,height:u32} {
 const entry=r4os.ico.chooseBest(bytes,preferred) catch return null;
 const image=r4os.ico.parseBmpImage(bytes,entry) catch return null;
 if(image.width==0 or image.height==0 or image.width>256 or image.height>256 or out.len<image.width*image.height)return null;
 for(0..image.height)|y|for(0..image.width)|x|{const p=r4os.ico.pixelAt(bytes,image,@intCast(x),@intCast(y)) orelse return null;out[y*image.width+x]=flatten(@truncate(p.rgb>>16),@truncate(p.rgb>>8),@truncate(p.rgb),p.alpha,bg);};
 return .{.width=image.width,.height=image.height};
}
// R4DRAW raster calls are bounded by the pinned ABI. Tile larger project images.
// Supply caller-owned scratch >= min(width, ABI max width)*min(height, ABI max height).
pub fn draw(canvas:r4os.gui.Canvas,x:i32,y:i32,width:u32,height:u32,pixels:[]const u32,scratch:[]u32) i32 {
 if(width==0 or height==0 or width>4096 or height>4096 or pixels.len<@as(usize,width)*height)return -1;
 const max_w=@min(128,r4os.abi.gui_raster_max_width);if(max_w==0)return -2;
 const max_h=@min(@min(128,r4os.abi.gui_raster_max_height),r4os.abi.gui_raster_max_pixels/max_w);
 if(max_h==0)return -2;
 var top:u32=0;while(top<height):(top+=max_h){var left:u32=0;while(left<width):(left+=max_w){
  const w=@min(max_w,width-left);const h=@min(max_h,height-top);
  if(scratch.len<@as(usize,w)*h)return -3;
  for(0..h)|row|@memcpy(scratch[row*w..][0..w],pixels[(top+row)*width+left..][0..w]);
  const px=std.math.add(i32,x,@intCast(left)) catch return -4;const py=std.math.add(i32,y,@intCast(top)) catch return -4;
  const rc=canvas.raster(px,py,w,h,1,scratch[0..@as(usize,w)*h]);if(rc<0)return rc;
 }}return 0;
}
