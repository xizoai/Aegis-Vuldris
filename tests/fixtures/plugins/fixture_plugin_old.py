"""A fixture plugin written against an OLDER contract version.

Used to prove that version mismatches are rejected with a clear reason and an
audit entry instead of being loaded on a guess.
"""

PLUGIN_API_VERSION = 0


class OldGrader:
    PLUGIN_API_VERSION = 0

    def grade(self, response_output, test_config):  # pragma: no cover - never called
        raise AssertionError("an incompatible plugin must never be invoked")
