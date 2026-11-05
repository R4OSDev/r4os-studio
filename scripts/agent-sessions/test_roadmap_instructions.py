"""Qualify the bound cleanup contract and preserve the exact saved sources."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

import test_runs as fixtures
from instructions import compose
from profile import PROFILE, permission_tools
from run_store import admit, get_run
from session_store import encode
from system_prompt import read, update


CONTRACT = Path(__file__).resolve().parents[2] / 'shared/project-roadmap-instructions.txt'


class RoadmapInstructions(unittest.TestCase):
    setUp = fixtures.Runs.setUp
    tearDown = fixtures.Runs.tearDown
    open = fixtures.Runs.open

    def frozen(self, custom=False):
        if custom: update(self.projects, {'revision': 0, 'text': 'Own unchanged global instructions. Keep my notes and formatting.\n'})
        path = self.projects / self.pid / 'Workspace/Agents.md'
        path.write_text('Own project instructions. Historical external roadmap https://roadmap.example.invalid/ must not gain permissions.\n')
        with self.open() as store:
            settings = {**self.settings, 'permissions': {'studio.' + t: False for t in permission_tools(PROFILE)}}
            store.db.execute('UPDATE sessions SET settings=?,engine=?', (encode(settings), encode({'profile': PROFILE}))); store.db.commit()
            run, _ = admit(store, self.sid, self.data, self.providers)
            config = json.loads(get_run(store, run['id'])['config'])
        return config, path

    def test_default_and_custom_global_sources_and_agents_file_remain_exact(self):
        for custom in (False, True):
            # Separate fixtures keep snapshot/default tests independent.
            if custom:
                self.tearDown(); self.setUp()
            config, agents = self.frozen(custom)
            original, raw_agents, global_source = deepcopy(config), agents.read_bytes(), read(self.projects)
            db_file = self.projects / '.studio/Settings.sqlite'
            raw_db = db_file.read_bytes() if db_file.exists() else None
            result = compose(config)
            # The complete source enters the common base. Managed SDK/shortcut
            # guidance is rendered once with the current feature contract.
            from instructions import base
            self.assertIn(config['systemPrompt']['text'], base(config))
            if custom: self.assertIn(config['systemPrompt']['text'], result)
            self.assertIn(config['projectInstructions']['text'], result)
            self.assertIn(CONTRACT.read_text(), result)
            self.assertEqual(config, original)
            self.assertEqual(agents.read_bytes(), raw_agents)
            self.assertEqual(read(self.projects), global_source)
            self.assertEqual(db_file.read_bytes() if db_file.exists() else None, raw_db)
            self.assertFalse(any(config['permissions'].values()))
            self.assertEqual(config['systemPrompt']['sha256'], hashlib.sha256(global_source['text'].encode()).hexdigest())

    def test_off_and_skill_owners_receive_only_actual_capabilities(self):
        config, _ = self.frozen()
        disabled = compose({**config, 'roadmapEnabled': False})
        self.assertIn('Roadmap tools are disabled for this run', disabled)
        self.assertNotIn('STUDIO PROJECT ROADMAP CONTRACT', disabled)
        skill_text = 'Own unchanged Skill Manager instructions.'
        skill = {'owner': {'type': 'skill', 'id': self.pid}, 'roadmapEnabled': True,
                 'skillManagerPrompt': {'text': skill_text, 'sha256': hashlib.sha256(skill_text.encode()).hexdigest()},
                 'engine': {'profile': 'studio-skill-tools-v2'}, 'permissions': {}}
        self.assertIn(skill_text, compose(skill))
        self.assertNotIn('STUDIO ROADMAP', compose(skill))
        self.assertNotIn('STUDIO PROJECT ROADMAP', compose(skill))
        legacy = {k: v for k, v in config.items() if k not in ('owner', 'roadmapEnabled')}
        self.assertNotIn('STUDIO ROADMAP', compose(legacy))
