"""Native input boundaries without credentials, inference or user state."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from goal_contract import native_goal, objective, save_params, capability, STATUSES
import profile


class GoalContracts(unittest.TestCase):
    def native(self):
        return {'threadId': 'own-thread', 'objective': 'Own goal', 'status': 'paused',
                'tokensUsed': 37, 'timeUsedSeconds': 12, 'createdAt': 1, 'updatedAt': 2}

    def test_scalar_limit_and_native_whitespace_match_without_utf16_truncation(self):
        self.assertEqual(objective('\u2003' + '😀' * 4000 + '\u3000'), '😀' * 4000)
        self.assertEqual(objective('\x1cOwn\x1c'), '\x1cOwn\x1c')
        for value in ('😀' * 4001, '\ud800', 'bad\x00text', ''):
            with self.subTest(value=value[:8]), self.assertRaises(ValueError): objective(value)
        self.assertEqual(objective('\n\u2003', allow_empty=True), '')

    def test_projection_is_thread_bound_exact_status_and_preserves_reported_usage(self):
        for status in STATUSES:
            raw = {**self.native(), 'status': status, 'private': 'never expose', 'tokenBudget': None}
            result = native_goal(raw, 'own-thread')
            self.assertEqual(result['tokensUsed'], 37); self.assertEqual(result['status'], status)
            self.assertNotIn('private', result); self.assertIsNone(result['tokenBudget'])
        for raw in ({**self.native(), 'threadId': 'foreign'}, {**self.native(), 'status': 'stopped'},
                    {**self.native(), 'tokensUsed': True}, {**self.native(), 'timeUsedSeconds': -1}):
            with self.assertRaises(ValueError): native_goal(raw, 'own-thread')

    def test_save_has_no_activation_budget_or_unchanged_objective_reset(self):
        method, params = save_params('own-thread', ' Own goal ', self.native())
        self.assertEqual(method, 'thread/goal/set')
        self.assertEqual(params, {'threadId': 'own-thread', 'origin': 'user', 'status': 'paused'})
        self.assertEqual(save_params('own-thread', 'Changed', self.native())[1]['objective'], 'Changed')
        self.assertEqual(save_params('own-thread', ' \n'), ('thread/goal/clear', {'threadId': 'own-thread', 'origin': 'user'}))

    def test_native_schema_has_real_images_and_no_general_file_or_stopped_status(self):
        root = Path(__file__).resolve().parents[2]
        schema = json.loads((root / 'shared/agent-input-native-contracts.json').read_text())
        self.assertEqual(schema['ThreadGoalStatus']['enum'], list(STATUSES))
        inputs = schema['UserInput']['oneOf']
        tags = [entry['properties']['type']['enum'][0] for entry in inputs]
        self.assertIn('localImage', tags); self.assertNotIn('input_file', tags)
        self.assertEqual(schema['ThreadGoalMutationOrigin']['enum'], ['user', 'automatic'])
        self.assertFalse(capability()['budgetControls']); self.assertTrue(capability()['requiresGoalWorker'])

    def test_only_explicit_qualified_goal_runtime_enables_goals_and_no_other_native_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); binary = root / 'codex'; binary.write_text('fixture, not executed')
            home = root / 'provider'; home.mkdir()
            (home / 'models_cache.json').write_text(json.dumps({'models': [{'slug': 'own-model'}]}))
            features = json.loads((Path(__file__).parent / 'features.json').read_text())
            with patch.object(profile, 'digest', return_value=profile.CODEX_SHA256):
                normal, _ = profile.prepare(binary, home, root / 'normal', features)
                goal, _ = profile.prepare(binary, home, root / 'goal', features, goals_enabled=True)
                with self.assertRaises(ValueError): profile.prepare(binary, home, root / 'invalid', [], goals_enabled=True)
            def switches(args):
                return dict(args[i+1].split('=', 1) for i, x in enumerate(args) if x == '-c')
            before, after = switches(normal), switches(goal)
            self.assertEqual(before['features.goals'], 'false'); self.assertEqual(after['features.goals'], 'true')
            self.assertEqual({k: v for k, v in before.items() if k != 'features.goals'},
                             {k: v for k, v in after.items() if k != 'features.goals'})
            self.assertEqual(after['features.collab'], 'false'); self.assertEqual(after['features.apps'], 'false')
