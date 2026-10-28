"""Bounded Poppler text extraction inside the fixed private decoder namespace."""
import hashlib
import json
import re
import resource
import selectors
import subprocess
import sys
import time

LIMIT=2*1024*1024


def bounded(args,limit,seconds):
    process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ,'out');selector.register(process.stderr,selectors.EVENT_READ,'err')
    output=bytearray();errors=bytearray();truncated=False;deadline=time.monotonic()+seconds
    try:
        while selector.get_map():
            if time.monotonic()>deadline:raise TimeoutError()
            for key,_ in selector.select(.1):
                chunk=key.fileobj.read1(65536)
                if not chunk:selector.unregister(key.fileobj);continue
                if key.data=='out':
                    output.extend(chunk[:max(0,limit+1-len(output))])
                    if len(output)>limit:truncated=True;process.kill()
                else:errors.extend(chunk[:max(0,16384-len(errors))])
        process.wait(timeout=1)
        return bytes(output[:limit]),bytes(errors),process.returncode,truncated
    finally:
        selector.close()
        if process.poll() is None:process.kill();process.wait()
        process.stdout.close();process.stderr.close()


def result(text='',**metadata):
    data=text.encode('utf-8')
    return {'mode':'pdfText','mediaType':'application/pdf','extractedBytes':len(data),
        'extractedSha256':hashlib.sha256(data).hexdigest(),'readable':bool(text.strip()),
        'truncated':False,'_text':text,**metadata}


def main():
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(10,10));resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    version=subprocess.run(['/usr/bin/pdftotext','-v'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=2)
    if b'pdftotext version 25.03.0' not in version.stderr:raise ValueError('Unqualified PDF decoder.')
    info,error,code,large=bounded(['/usr/bin/pdfinfo','-enc','UTF-8','/input'],65536,4)
    if b'Incorrect password' in error:return result(limitation='Encrypted PDF: text cannot be read. The original is retained; attach an unlocked copy or text.',encrypted=True)
    if code or large:raise ValueError('Invalid PDF information.')
    pages=re.search(rb'^Pages:\s+(\d+)\s*$',info,re.M)
    if not pages or not 0<int(pages[1])<=100000:raise ValueError('Invalid PDF page count.')
    pages=int(pages[1])
    if re.search(rb'^Encrypted:\s+yes\b',info,re.M):
        return result(pages=pages,encrypted=True,limitation='Encrypted PDF: text access is unavailable. The original is retained; attach an unlocked copy or text.')
    if pages>128:return result(pages=pages,limitation='PDF exceeds128 pages. The original is retained; attach a smaller document or text excerpt.')
    try:raw,error,code,truncated=bounded(['/usr/bin/pdftotext','-enc','UTF-8','-eol','unix','-layout','-nopgbrk','-f','1','-l',str(pages),'/input','-'],LIMIT,7)
    except (OSError,TimeoutError,subprocess.TimeoutExpired):
        return result(pages=pages,limitation='PDF text extraction exceeded its resource limit. The original is retained; attach a smaller document or text.')
    if code and not truncated:return result(pages=pages,limitation='PDF text extraction failed. The original is retained; attach text or a different PDF export.')
    if truncated:
        # Only the final partial UTF8 scalar may be removed from this explicitly
        # incomplete prefix. Invalid interior encoding still rejects extraction.
        for end in range(4):
            try:text=(raw if end==0 else raw[:-end]).decode('utf-8');break
            except UnicodeError:
                if end==3:raise
    else:text=raw.decode('utf-8')
    if '\x00' in text:raise ValueError('PDF text includes NUL bytes.')
    limitation=('Only an initial2 MiB text prefix was extracted. The remainder, embedded images, scans and full layout were not read.' if truncated
        else 'Text extraction only. Embedded images, scans and full visual layout were not read.' if text.strip()
        else 'No extractable text. Scanned pages and embedded images were not read; attach OCR text or images.')
    return result(text,pages=pages,truncated=truncated,limitation=limitation)


if __name__=='__main__':
    try:print(json.dumps(main(),ensure_ascii=False))
    except Exception:print(json.dumps({'error':'PDF validation or bounded text extraction failed. No document content was read by the model.'}));sys.exit(1)
