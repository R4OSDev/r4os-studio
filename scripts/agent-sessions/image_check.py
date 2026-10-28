"""Fixed raster decoder. Runs only in a private, networkless mount namespace."""
import json
import resource
import sys
import warnings

class InputFault(ValueError):pass

def main():
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(6,6))
    resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    from PIL import Image,ImageFile,__version__
    if __version__!='11.1.0':raise ValueError('The raster decoder needs qualification.')
    Image.MAX_IMAGE_PIXELS=40_000_000;ImageFile.LOAD_TRUNCATED_IMAGES=False
    warnings.simplefilter('error',Image.DecompressionBombWarning)
    with Image.open('/input',formats=['PNG','JPEG','WEBP']) as image:
        width,height=image.size;kind=image.format
        if not 0<width<=16384 or not 0<height<=16384 or width*height>40_000_000:
            raise InputFault('Image dimensions exceed16384 per axis or40 million pixels.')
        if getattr(image,'n_frames',1)!=1:raise InputFault('Animated images are not supported. Attach one still frame.')
        image.verify()
    with Image.open('/input',formats=['PNG','JPEG','WEBP']) as image:
        image.load();transparent=image.convert('RGBA').getchannel('A').getextrema()[0]<255
    print(json.dumps({'mediaType':{'PNG':'image/png','JPEG':'image/jpeg','WEBP':'image/webp'}[kind],
        'width':width,'height':height,'transparent':bool(transparent),'mode':'localImage','decoder':'Pillow '+__version__}))


if __name__=='__main__':
    try:main()
    except InputFault as error:
        print(json.dumps({'error':str(error)}));sys.exit(1)
    except Exception:
        print(json.dumps({'error':'The image is invalid, animated, truncated, or exceeds the decoder limits.'}));sys.exit(1)
