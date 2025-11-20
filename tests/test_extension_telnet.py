import pytest

# Telnet extension is deprecated after asyncio migration
# It relied on twisted.conch which has been removed
pytestmark = pytest.mark.skip(reason="TelnetConsole is deprecated after asyncio migration")

# Empty test module - all functionality is deprecated
# Original tests required Twisted's conch library which is no longer supported
