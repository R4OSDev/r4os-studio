"""Bounded private raster preview; no network, original writes or model calls."""
import base64
import io
import json
import resource
import sys
import warnings


def main():
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(6,6))
    resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    from PIL import Image,ImageFile,ImageOps,__version__
    if __version__!='11.1.0':raise ValueError('The raster decoder needs qualification.')
    Image.MAX_IMAGE_PIXELS=40_000_000;ImageFile.LOAD_TRUNCATED_IMAGES=False
    warnings.simplefilter('error',Image.DecompressionBombWarning)
    with Image.open('/input',formats=['PNG','JPEG','WEBP']) as image:
        width,height=image.size
        if not 0<width<=16384 or not 0<height<=16384 or width*height>40_000_000 or getattr(image,'n_frames',1)!=1:raise ValueError()
        image.verify()
    with Image.open('/input',formats=['PNG','JPEG','WEBP']) as image:
        # JPEG draft reduces decoder memory. Alpha remains alpha, including
        # palette transparency; no background color is composited.
        image.draft('RGB',(1024,1024))
        image=ImageOps.exif_transpose(image)
        if image.mode=='P':image=image.convert('RGBA')
        image.thumbnail((1024,1024),Image.Resampling.LANCZOS)
        image=image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
        for _ in range(7):
            output=io.BytesIO();image.save(output,'PNG',compress_level=6)
            raw=output.getvalue()
            if 0<len(raw)<=393216:
                print(json.dumps({'png':base64.b64encode(raw).decode(),'width':image.width,'height':image.height}));return
            image=image.resize((max(1,image.width*3//4),max(1,image.height*3//4)),Image.Resampling.LANCZOS)
    raise ValueError('Preview exceeds its size bound.')


if __name__=='__main__':
    try:main()
    except Exception:
        print(json.dumps({'error':'The original image preview is unavailable. Original bytes were preserved.'}));sys.exit(1)
