"""cu-specific configuration and helpers — Phase 3a placeholder.

# TODO M3a.1: define CU_OBSERVATION_COMMANDS once we know which cu
# sub-commands return reasoning-friendly data. From inherited-artifacts.md
# §3, the tentative set is:
#
#     CU_OBSERVATION_COMMANDS = frozenset({"snapshot", "screenshot", "ocr", "tell"})
#
# but this needs validation against computer-pilot's actual command surface.

# TODO M3a.1: implement cu_truncate_snapshot for cu's snapshot JSON shape.
# cu uses macOS accessibility tree, not browser DOM, so the format will be
# different from bp's element list.

# TODO M3a.1: implement cu_skill_path() with the same env-var-first strategy
# as caliper_browser_pilot.tools.bp_skill_path. The env var name should be
# CALIPER_CU_SKILL_PATH.
"""
