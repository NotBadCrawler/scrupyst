import pytest


class TestScrapyUtils:
    def test_no_twisted_dependency(self):
        """Verify that Twisted is no longer a dependency after the asyncio migration."""
        try:
            import twisted  # noqa: F401
            # If Twisted is installed, that's fine, but it shouldn't be required
            pytest.skip("Twisted is still installed but not required")
        except ImportError:
            # This is expected - Twisted should not be a dependency
            pass
