"""Agent Dealer rename and backwards-compatibility checks."""

import subprocess
import sys
import unittest

import agent_collaboration
import agent_dealer
from agent_collaboration.store import TaskStore as LegacyTaskStore
from agent_dealer.store import TaskStore


class RenameCompatibilityTests(unittest.TestCase):
    def test_legacy_package_reexports_new_implementation(self):
        self.assertEqual(agent_collaboration.__version__, agent_dealer.__version__)
        self.assertIs(LegacyTaskStore, TaskStore)

    def test_both_module_entry_points_report_same_version(self):
        versions = []
        for module_name in ("agent_dealer", "agent_collaboration"):
            result = subprocess.run(
                [sys.executable, "-m", module_name, "--version"],
                check=True,
                capture_output=True,
                text=True,
            )
            versions.append(result.stdout.strip())
        self.assertEqual(versions, [agent_dealer.__version__, agent_dealer.__version__])


if __name__ == "__main__":
    unittest.main()
