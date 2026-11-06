"""Display inventory reuse; executable selections keep their full validators."""
import copy
import hashlib
import time
from inventory_reads import collect, watch
from sdk_sets import profile_revision, resolve, summary


def binding(manager):
    manager.refresh_profile()
    return (profile_revision(manager.state), manager.inventory_epoch, profile_revision(manager.external))


def generation(manager, key):
    return manager.inventory_nonce + ':' + ':'.join(map(str, key))


def snapshot(manager):
    with manager.lock:
        key = binding(manager)
        return key, copy.deepcopy(manager.state), copy.deepcopy(manager.catalogs), copy.deepcopy(manager.sdk_sets)


def prepare(manager, saved):
    from service import KINDS, public
    from r4upack import selected
    key, state, catalogs, sdk_sets = saved
    with collect() as facts:
        watch(manager.profile)
        watch(manager.root / 'Profiles/r4upack.json')
        watch(manager.root / 'Profiles/sdk-host-maintenance.json')
        inventories = {}; packer_error = None
        for kind in KINDS:
            try:
                inventories[kind] = manager.installed(kind)
            except (OSError, ValueError, TypeError, KeyError) as error:
                if kind != 'r4upack':
                    raise
                inventories[kind] = []; packer_error = str(error)[:500]
        try:
            packer = selected(manager.root, inventories['r4upack'])
            if packer is None and (manager.root / 'Profiles/r4upack.json').exists():
                packer_error = 'The selected R4UPack profile is missing or changed. Existing files were preserved.'
        except (OSError, ValueError, TypeError, KeyError) as error:
            packer = None; packer_error = str(error)[:500]
        sdks = {value['id']: value for value in inventories['sdk'] + catalogs.get('sdk', {}).get('versions', [])}
        for ident, record in sdks.items():
            try:
                sdk_sets[ident] = resolve(manager, record, fetch=False)
            except (OSError, ValueError, KeyError, TypeError) as error:
                sdk_sets[ident] = {'state': 'unavailable', 'reason': str(error)[:500]}
        components = {}
        for kind in KINDS:
            catalog = catalogs.get(kind, {})
            active = packer if kind == 'r4upack' else state['defaults'].get(kind)
            components[kind] = {'installed': [public(record) for record in inventories[kind]],
                                'available': [public(record) for record in catalog.get('versions', [])],
                                'activeId': active['id'] if active else None,
                                'latestId': catalog.get('latestId'), 'checkedAt': catalog.get('checkedAt'),
                                'error': packer_error if kind == 'r4upack' and packer_error else catalog.get('error'),
                                'hasMore': catalog.get('hasMore', False)}
        for record in components['sdk']['installed'] + components['sdk']['available']:
            value = sdk_sets.get(record['id'], {'state': 'unresolved', 'reason': 'Check SDK versions to resolve the matching packages.'})
            record['sdkSet'] = summary(value, inventories, state['defaults'])
    return components, facts


def progress(manager):
    with manager.lock:
        key = binding(manager)
        cached = manager.inventory_cache
        return {'enabled': True, 'job': copy.deepcopy(manager.job), 'profileRevision': key[0],
                'generation': generation(manager, key), 'features': {'componentProgress': 1},
                'inventoryRevision': cached['revision'] if cached and cached['binding'] == key else None}


def status(manager, refresh=False):
    from service import now
    # Expensive validation serializes only with other inventory readers. Job
    # progress and mutation admission never wait behind this display read lock.
    with manager.inventory_read_lock:
        for _ in range(2):
            saved = snapshot(manager); key = saved[0]; cached = manager.inventory_cache
            reused = bool(not refresh and cached and cached['binding'] == key
                          and cached['expires'] > time.monotonic() and cached['facts'].unchanged())
            if reused:
                components, facts = cached['components'], cached['facts']
                checked, revision = cached['checkedAt'], cached['revision']
            else:
                components, facts = prepare(manager, saved)
                stable = facts.unchanged()
                if facts.changed:
                    continue
                checked = now()
                revision = hashlib.sha256(repr((key, sorted((str(path), value) for path, value in facts.files.items()))).encode()).hexdigest() if stable else None
            with manager.lock:
                if binding(manager) != key:
                    continue
                job = copy.deepcopy(manager.job)
                maintenance = (manager.root / 'Profiles/sdk-host-maintenance.json').exists()
                if not reused:
                    manager.inventory_cache = ({'binding': key, 'components': components, 'facts': facts,
                        'checkedAt': checked, 'revision': revision, 'expires': time.monotonic() + 30} if revision else None)
            return {'enabled': True, 'components': copy.deepcopy(components), 'job': job,
                    'features': {'sdkSets': 1, 'sdkSelection': 1, 'sdkProfiles': 1, 'sdkMigration': 1, 'componentProgress': 1},
                    'profileRevision': key[0], 'generation': generation(manager, key),
                    'inventory': {'revision': revision, 'checkedAt': checked, 'reused': reused},
                    'message': 'Explicit SDK maintenance is pending.' if maintenance else 'Downloads and active defaults are managed independently.'}
    raise ValueError('The component inventory changed while checking it. Refresh after the current operation; existing files were preserved.')
