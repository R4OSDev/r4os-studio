#!/usr/bin/env python3
"""Explicit local decoder installation; never called by the web app/updater."""
import json
import os
import subprocess
import sys


def main():
    if '--check' not in sys.argv:
        if os.getuid()!=0:raise SystemExit('Run the explicit local installer as root, or use --check.')
        subprocess.run(['/usr/bin/apt-get','--assume-yes','--no-install-recommends','install','python3-pil=11.1.0-5+deb13u4'],check=True)
    from PIL import Image,features,__version__
    if __version__!='11.1.0' or not features.check('webp'):raise SystemExit('The qualified Pillow11.1.0/WebP decoder is unavailable.')
    import io
    for kind in ('PNG','JPEG','WEBP'):
        buf=io.BytesIO();Image.new('RGB',(2,2),'purple').save(buf,kind);buf.seek(0)
        with Image.open(buf,formats=[kind]) as image:image.load();assert image.size==(2,2)
    print(json.dumps({'pillow':__version__,'formats':['PNG','JPEG','WEBP'],'projectAndProviderDataChanged':False,'serviceRestart':False}))


if __name__=='__main__':main()
