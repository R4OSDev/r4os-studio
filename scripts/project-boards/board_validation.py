import re
import unicodedata
from store import ProjectFault

MAX_BOARDS=100
MAX_COLUMNS=32
MAX_CARDS=1000
MAX_LABELS=64
MAX_CHECKLIST=100
COLORS=('purple','blue','green','yellow','orange','pink','gray')

def fields(value,required=(),optional=()):
    if not isinstance(value,dict) or set(value)-set(required)-set(optional) or set(required)-set(value):
        raise ProjectFault('Unexpected Board fields.',400)

def identity(value):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}',value):raise ProjectFault('Invalid Board identity.',400)
    return value

def integer(value,minimum=1,maximum=9007199254740991):
    if type(value) is not int or not minimum<=value<=maximum:raise ProjectFault('Invalid Board revision or position.',400)
    return value

def text(value,maximum=120,multiline=False,empty=False):
    if not isinstance(value,str):raise ProjectFault('Enter Board text.',400)
    if not multiline:value=value.strip()
    if (len(value)>maximum or (not empty and not value.strip())
            or any(0xd800<=ord(c)<=0xdfff or ord(c)==127 or (ord(c)<32 and not (multiline and c in '\n\r\t')) for c in value)):
        raise ProjectFault('Board text is empty, too long or contains unsupported characters.',400)
    return value

def name_key(value):return unicodedata.normalize('NFC',value).casefold()

def order(value,expected):
    if not isinstance(value,list) or len(value)!=len(expected) or any(not isinstance(v,str) for v in value) or set(value)!=set(expected):
        raise ProjectFault('The complete original Board order changed. Reload before moving.',409)
    return value
