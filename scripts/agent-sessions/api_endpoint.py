"""Fixed API endpoint policy. No HTTP request or credential forwarding here."""
import ipaddress
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit, urlunsplit

sys.path.append(str(Path(__file__).resolve().parents[1] / 'projects'))
from store import ProjectFault

LOCAL = tuple(ipaddress.ip_network(value) for value in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','127.0.0.0/8','fc00::/7','::1/128'))
CONTROL_PORTS = {22,53,2375,2376,3306,4011,5010,5432,6379}


def address_allowed(value, local):
    try:
        address=ipaddress.ip_address(value)
        if getattr(address,'ipv4_mapped',None) is not None: return False
        if address.is_multicast or address.is_unspecified or address.is_link_local: return False
        return any(address.version==network.version and address in network for network in LOCAL) if local else address.is_global
    except ValueError: return False


def endpoint(value, kind):
    if (not isinstance(value,str) or not 1<=len(value)<=2048 or re.search(r'[\x00-\x20\x7f\\]',value)):
        raise ProjectFault('Enter a valid API base URL without credentials, query or fragment.',400)
    try:
        parsed=urlsplit(value);host=parsed.hostname;port=parsed.port
        if (parsed.username is not None or parsed.password is not None or not host or parsed.query or parsed.fragment
                or parsed.scheme not in ('https','http') or '%' in parsed.netloc): raise ValueError()
        local=kind=='local'
        if not local and parsed.scheme!='https': raise ValueError()
        if port is not None and not 1<=port<=65535: raise ValueError()
        port=port or (443 if parsed.scheme=='https' else 80)
        host=host.lower().rstrip('.')
        if local and host=='localhost': host='127.0.0.1'
        try: address=ipaddress.ip_address(host)
        except ValueError: address=None
        if address:
            if not address_allowed(str(address),local): raise ValueError()
            host=address.compressed
        else:
            # Local IP/localhost is explicit; public DNS is revalidated and
            # pinned before transport use. DNS names never authorize private IPs.
            if (local or len(host)>253 or host in ('metadata.google.internal','metadata','localhost','localhost.localdomain')
                    or host.endswith('.localhost') or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',part) for part in host.split('.'))): raise ValueError()
        if local and port in CONTROL_PORTS: raise ValueError()
        path=parsed.path.rstrip('/')
        if (path and not re.fullmatch(r'(?:/[A-Za-z0-9._~-]+)*',path)) or any(part in ('.','..') for part in path.split('/')): raise ValueError()
        authority='['+host+']' if ':' in host else host
        if port!=(443 if parsed.scheme=='https' else 80):authority+=':'+str(port)
        origin=parsed.scheme+'://'+authority
        return {'baseUrl':urlunsplit((parsed.scheme,authority,path,'','')),'origin':origin,'local':local}
    except (ValueError,UnicodeError):
        raise ProjectFault('Use HTTPS for public APIs or an explicit local IP/localhost model endpoint. Credentials, metadata/control targets and noncanonical paths are not allowed.',400) from None


def resolved_addresses(value, addresses):
    """Mandatory before opening a future transport socket, including DNS refresh.

    Transport must connect to one of these exact checked IPs, keep the original
    TLS server name, verify certificates and reject redirects. Never resolve
    again between validation and connect or forward credentials on a redirect.
    """
    values=sorted(set(addresses))
    if not values or not all(address_allowed(address,value['local']) for address in values):
        raise ProjectFault('The API endpoint resolved outside its allowed network scope.',400)
    return values
