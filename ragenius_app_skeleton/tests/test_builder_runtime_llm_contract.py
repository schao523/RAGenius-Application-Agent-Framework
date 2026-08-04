import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.builder_runtime import derive_builder_config_json
from backend.app.llm_runtime import resolve_task_model
from ragenius_builder.flask_scaffold.storage import DEFAULT_APP_CONFIG_SETTINGS


class BuilderRuntimeLlmContractTests(unittest.TestCase):
    def _app_record(self):
        return {
            'id': 'app-1',
            'name': 'Bible Helper',
            'slug': 'bible-helper',
            'description': 'desc',
            'starter_questions': ['q1'],
        }

    def test_derive_builder_config_json_merges_partial_nested_llm_with_defaults(self):
        settings_record = {
            'config_settings': {
                'llm': {
                    'provider': 'deepseek',
                    'models': {
                        'planner': 'deepseek-reasoner',
                        'adapter_generation': 'deepseek-reasoner',
                    },
                    'temperature': {
                        'planner': 0.55,
                    },
                }
            }
        }
        config_json = derive_builder_config_json(self._app_record(), settings_record, {'content': '# Mission\n- Help', 'version': 'v1'})
        llm_settings = config_json['meta']['llm_settings']

        self.assertEqual(llm_settings['provider'], 'deepseek')
        self.assertEqual(llm_settings['models']['planner'], 'deepseek-reasoner')
        self.assertEqual(llm_settings['models']['adapter_generation'], 'deepseek-reasoner')
        self.assertEqual(
            llm_settings['models']['answer_generation'],
            DEFAULT_APP_CONFIG_SETTINGS['llm']['models']['answer_generation'],
        )
        self.assertEqual(llm_settings['temperature']['planner'], 0.55)
        self.assertEqual(
            llm_settings['temperature']['answer_generation'],
            DEFAULT_APP_CONFIG_SETTINGS['llm']['temperature']['answer_generation'],
        )

    def test_derive_builder_config_json_migrates_legacy_flat_llm_keys_to_canonical_nested_shape(self):
        settings_record = {
            'config_settings': {
                'provider': 'deepseek',
                'planner_model': 'deepseek-reasoner',
                'answer_model': 'deepseek-v4-flash',
                'temperature': 0.4,
                'base_url': 'https://api.deepseek.com',
            }
        }
        config_json = derive_builder_config_json(self._app_record(), settings_record, {'content': '# Mission\n- Help', 'version': 'v1'})
        llm_settings = config_json['meta']['llm_settings']

        self.assertEqual(llm_settings['provider'], 'deepseek')
        self.assertEqual(llm_settings['models']['planner'], 'deepseek-reasoner')
        self.assertEqual(llm_settings['models']['answer_generation'], 'deepseek-v4-flash')
        self.assertEqual(llm_settings['temperature']['planner'], 0.4)
        self.assertEqual(llm_settings['temperature']['answer_generation'], 0.4)
        self.assertEqual(llm_settings['base_url'], 'https://api.deepseek.com')

    def test_resolve_task_model_no_longer_reads_flat_legacy_task_keys_directly(self):
        config = resolve_task_model(
            {
                'provider': 'deepseek',
                'planner_model': 'deepseek-reasoner',
                'answer_model': 'deepseek-v4-flash',
            },
            'planner',
        )
        self.assertIsNone(config)


if __name__ == '__main__':
    unittest.main()
