"""Shared admission guard; deletion cannot pass between capture and commit."""
import functools
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('studio_catalog_lifecycle',Path(__file__).resolve().parents[1]/'skills/lifecycle.py')
api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)

def guarded(fn):
    @functools.wraps(fn)
    def call(first,*args,**kwargs):
        if fn.__module__=='message_store' and len(args)>1 and isinstance(args[1],dict) and args[1].get('mode')=='steer':return fn(first,*args,**kwargs)
        from store import ProjectFault
        from owner import skills_root,skill_workspace
        store=first.store if hasattr(first,'store') else first
        with api.lock(skills_root(store.projects),fault=ProjectFault):
            if store.owner_type=='skill':skill_workspace(store.projects,store.owner_id)
            return fn(first,*args,**kwargs)
    return call

def initialize(fn):
    @functools.wraps(fn)
    def call(self,projects,r4os,ident,kind='project'):
        from store import ProjectFault
        from owner import skills_root
        if kind!='skill':return fn(self,projects,r4os,ident,kind)
        with api.lock(skills_root(projects),ident='lifetime-'+ident,fault=ProjectFault):return fn(self,projects,r4os,ident,kind)
    return call


def goal_guard(fn):
    @functools.wraps(fn)
    def call(self,sid,data):
        if data.get('action')!='play':return fn(self,sid,data)
        return guarded(fn)(self,sid,data)
    return call
