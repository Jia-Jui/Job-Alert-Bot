from __future__ import annotations

import os
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_alert_bot.config import DEFAULT_INCLUDE_KEYWORDS, load_app_config


class ConfigTests(unittest.TestCase):
    def test_link_resolution_defaults_are_safe(self) -> None:
        old_values = {name: os.environ.get(name) for name in (
            "JOB_ALERT_ENABLE_ADVANCED_LINK_DISCOVERY",
            "JOB_ALERT_LINK_DISCOVERY_TIMEOUT_SECONDS",
            "JOB_ALERT_LINK_DISCOVERY_MAX_PAGES",
            "JOB_ALERT_COMPANY_PRIORITIES",
            "JOB_ALERT_PREFERRED_COMPANIES",
        )}
        try:
            for name in old_values:
                os.environ.pop(name, None)
            config = load_app_config()
        finally:
            for name, value in old_values.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

        self.assertFalse(config.enable_advanced_link_discovery)
        self.assertEqual(config.link_discovery_timeout_seconds, 12)
        self.assertEqual(config.link_discovery_max_pages, 2)
        self.assertEqual(config.company_priority_overrides, {})
        self.assertEqual(config.preferred_company_names, [])
        self.assertEqual(config.include_keywords, DEFAULT_INCLUDE_KEYWORDS)


if __name__ == "__main__":
    unittest.main()
