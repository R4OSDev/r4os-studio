/* Studio companion for project sources. Uses the project's matched SDK/Contract. */
#ifndef STUDIO_PROJECT_IMAGES_H
#define STUDIO_PROJECT_IMAGES_H
#include <r4os/r4os.h>
#include <r4os/app_resources.h>
#include <stddef.h>
static int32_t studio_image_read(R4App *app,uint32_t kind,uint32_t index,const char *name,uint8_t *out,uint32_t capacity) {
 if (!app || !name || !out || !R4_RESOURCE_SYS_HAS(app,module_resource_read)) return -1;
 R4Resources resources=r4_app_resources(app);uint8_t path[132]={0};
 if(r4_resources_program_module_path(&resources,path,128)<=0)return -2;
 int32_t result=((R4SysModuleResourceReadFn)(uintptr_t)app->system.table->module_resource_read)(path,kind,index,(const uint8_t *)name,out,capacity);
 return result>0 && (uint32_t)result<=capacity?result:-3;
}
static uint32_t studio_rgb(uint8_t r,uint8_t g,uint8_t b,uint8_t a,uint32_t bg) {
 uint32_t inv=255u-a;
 return (((r*a+((bg>>16)&255u)*inv+127u)/255u)<<16)|(((g*a+((bg>>8)&255u)*inv+127u)/255u)<<8)|((b*a+(bg&255u)*inv+127u)/255u);
}
static int studio_rgba(const uint8_t *bytes,size_t length,uint32_t width,uint32_t height,uint32_t stride,uint32_t *out,size_t count,uint32_t background) {
 if(!bytes || !out || !width || !height || width>4096 || height>4096 || (uint64_t)width*height>16000000 || stride!=width*4 || length!=(size_t)stride*height || count<(size_t)width*height)return 0;
 for(size_t i=0;i<(size_t)width*height;i++)out[i]=studio_rgb(bytes[i*4],bytes[i*4+1],bytes[i*4+2],bytes[i*4+3],background);
 return 1;
}
static uint16_t studio_u16(const uint8_t *p){return (uint16_t)p[0]|((uint16_t)p[1]<<8);}
static uint32_t studio_u32(const uint8_t *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
/* This bounded companion consumes Studio's uncompressed32-bit DIB ICO outputs. */
static int studio_icon(const uint8_t *bytes,size_t length,uint32_t preferred,uint32_t *out,size_t capacity,uint32_t bg,uint32_t *width,uint32_t *height) {
 if(!bytes || !out || !width || !height || length<6 || studio_u16(bytes)!=0 || studio_u16(bytes+2)!=1)return 0;
 uint32_t count=studio_u16(bytes+4);if(!count || count>32 || length<6u+(size_t)count*16u)return 0;
 for(uint32_t i=0;i<count;i++){
  const uint8_t *entry=bytes+6+i*16;uint32_t w=entry[0]?entry[0]:256,h=entry[1]?entry[1]:256;
  if(w!=preferred || h!=preferred)continue;
  uint32_t offset=studio_u32(entry+12),size=studio_u32(entry+8);
  if(offset>length || size>length-offset || size<40 || capacity<(size_t)w*h)return 0;
  const uint8_t *dib=bytes+offset;
  if(studio_u32(dib)!=40 || studio_u32(dib+4)!=w || studio_u32(dib+8)!=h*2 || studio_u16(dib+12)!=1 || studio_u16(dib+14)!=32 || studio_u32(dib+16)!=0 || size<40u+(size_t)w*h*4)return 0;
  for(uint32_t y=0;y<h;y++)for(uint32_t x=0;x<w;x++){const uint8_t *p=dib+40+((size_t)(h-1-y)*w+x)*4;out[(size_t)y*w+x]=studio_rgb(p[2],p[1],p[0],p[3],bg);}
  *width=w;*height=h;return 1;
 }return 0;
}
/* Invoke only during a valid current window paint. Caller owns scratch buffers. */
static int32_t studio_image_draw(R4Canvas canvas,int32_t x,int32_t y,uint32_t width,uint32_t height,const uint32_t *pixels,size_t count,uint32_t *scratch,size_t capacity) {
 if(!canvas.paint || !canvas.paint->active || !pixels || !scratch || !width || !height || width>4096 || height>4096 || count<(size_t)width*height)return -1;
 R4Draw *draw=&canvas.paint->window->app->drawing;
 if(!draw->table || draw->table->size<offsetof(R4XStartR4Draw,gui_blit)+sizeof(uintptr_t) || !draw->table->gui_blit)return -2;
 R4DrawGuiBlitFn blit=(R4DrawGuiBlitFn)(uintptr_t)draw->table->gui_blit;
 uint32_t max_w=R4OS_GUI_RASTER_MAX_WIDTH<128?R4OS_GUI_RASTER_MAX_WIDTH:128;
 if(!max_w)return -2;
 uint32_t max_h=R4OS_GUI_RASTER_MAX_HEIGHT<128?R4OS_GUI_RASTER_MAX_HEIGHT:128;
 if(max_h>R4OS_GUI_RASTER_MAX_PIXELS/max_w)max_h=R4OS_GUI_RASTER_MAX_PIXELS/max_w;
 if(!max_h)return -2;
 for(uint32_t top=0;top<height;top+=max_h)for(uint32_t left=0;left<width;left+=max_w){
  uint32_t w=width-left<max_w?width-left:max_w,h=height-top<max_h?height-top:max_h;
  if(capacity<(size_t)w*h || (int64_t)x+left>INT32_MAX || (int64_t)y+top>INT32_MAX)return -3;
  for(uint32_t row=0;row<h;row++)for(uint32_t col=0;col<w;col++)scratch[(size_t)row*w+col]=pixels[(size_t)(top+row)*width+left+col];
  int32_t result=blit(x+(int32_t)left,y+(int32_t)top,w,h,1,scratch,w*h);if(result<0)return result;
 }return 0;
}
#endif
