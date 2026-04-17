#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."/..
cp backups/2026-04-17-generic-test-migration/test/test_family_member_agent_runtime.py test/test_family_member_agent_runtime.py
cp backups/2026-04-17-generic-test-migration/test/test_schedule_information_agent_runtime.py test/test_schedule_information_agent_runtime.py
cp backups/2026-04-17-generic-test-migration/test/test_external_contact_agent_runtime.py test/test_external_contact_agent_runtime.py
cp backups/2026-04-17-generic-test-migration/test/test_runtime_self_repair.py test/test_runtime_self_repair.py
printf 'Restored backed up test files.\n'
