"""Fixed, networkless image preparation. No project or credential filesystem."""
import hashlib
import json
from pathlib import Path
import resource
import struct
import sys
import warnings


def main():
    resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024));resource.setrlimit(resource.RLIMIT_CPU,(8,8));resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024*1024,64*1024*1024))
    from PIL import Image,ImageFile,ImageOps,__version__
    if __version__!='11.1.0':raise ValueError('Unqualified image decoder.')
    Image.MAX_IMAGE_PIXELS=40_000_000;ImageFile.LOAD_TRUNCATED_IMAGES=False;warnings.simplefilter('error',Image.DecompressionBombWarning)
    args=json.loads(sys.stdin.buffer.read(4097));fmt=args['format'];options=args.get('options',{})
    with Image.open('/input',formats=['PNG']) as original:
        if original.width*original.height>40_000_000 or getattr(original,'n_frames',1)!=1:raise ValueError('Image limit exceeded.')
        original.load();image=original.convert('RGBA');source_size=list(image.size)
    background=options.get('background','#00000000');rgba=tuple(bytes.fromhex(background[1:]))
    if len(rgba)==3:rgba=(*rgba,255)
    width=options.get('width',64 if fmt=='ico' else image.width);height=options.get('height',64 if fmt=='ico' else image.height)
    if 'width' in options and 'height' not in options:height=max(1,round(image.height*width/image.width))
    if 'height' in options and 'width' not in options:width=max(1,round(image.width*height/image.height))
    if fmt!='original' and (not 1<=width<=4096 or not 1<=height<=4096 or width*height>16_000_000):raise ValueError('Prepared image dimensions exceed4096 or16 million pixels.')
    if fmt=='ico' and (width>256 or height>256):raise ValueError('Bitmap ICO dimensions must be1–256.')
    if fmt=='original':
        if options:raise ValueError('Original copies do not accept transformations.')
        output=Path('/input').read_bytes()
    else:
        fit=options.get('fit','contain')
        resized=ImageOps.fit(image,(width,height),method=Image.Resampling.LANCZOS) if fit=='cover' else ImageOps.contain(image,(width,height),method=Image.Resampling.LANCZOS)
        canvas=Image.new('RGBA',(width,height),rgba);canvas.alpha_composite(resized,((width-resized.width)//2,(height-resized.height)//2));image=canvas
        if fmt=='png':
            import io
            stream=io.BytesIO();image.save(stream,format='PNG',optimize=False,compress_level=9);output=stream.getvalue()
        elif fmt=='rgba32':output=image.tobytes('raw','RGBA')
        elif fmt=='ico':
            stride=width*4;mask_stride=((width+31)//32)*4;pixels=image.tobytes('raw','BGRA',stride,-1);alpha=image.getchannel('A')
            mask=bytearray(mask_stride*height)
            for y in range(height):
                for x in range(width):
                    if alpha.getpixel((x,height-1-y))==0:mask[y*mask_stride+x//8]|=1<<(7-x%8)
            dib=struct.pack('<IiiHHIIiiII',40,width,height*2,1,32,0,len(pixels)+len(mask),0,0,0,0)+pixels+mask
            output=struct.pack('<HHHBBBBHHII',0,1,1,width%256,height%256,0,0,1,32,len(dib),22)+dib
        else:raise ValueError('Unsupported prepared format.')
    if not 0<len(output)<=64*1024*1024:raise ValueError('Prepared image size limit exceeded.')
    path=Path('/out/prepared');path.write_bytes(output);path.chmod(0o600)
    print(json.dumps({'size':len(output),'sha256':hashlib.sha256(output).hexdigest(),'format':fmt,'width':image.width,'height':image.height,'transparent':image.getchannel('A').getextrema()[0]<255,
        'transform':{'adapter':'studio-image-v1/Pillow11.1.0','sourceSize':source_size,'fit':options.get('fit','contain'),'background':background,'outputSize':list(image.size)},
        **({'pixelOrder':'RGBA','stride':image.width*4,'rowOrder':'top-down','alpha':'straight','headerBytes':0,'resourceFormat':'project-specific raw RGBA32; not an R4OS file standard'} if fmt=='rgba32' else {}),
        **({'encoding':'ICO BITMAPINFOHEADER/BI_RGB/32bpp BGRA bottom-up + AND mask'} if fmt=='ico' else {})}))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'error':str(error)[:200]}));sys.exit(1)
