from __future__ import annotations

import ssl as stdlib_ssl
from pathlib import Path

from scrapy.utils.python import to_bytes

# Keep old imports for backward compatibility with existing Twisted-based tests
try:
    from OpenSSL import SSL
    from twisted.internet import ssl

    TWISTED_AVAILABLE = True
except ImportError:
    TWISTED_AVAILABLE = False


def ssl_context_factory(
    keyfile="keys/localhost.key", certfile="keys/localhost.crt", cipher_string=None
):
    """Twisted-based SSL context factory (deprecated)."""
    if not TWISTED_AVAILABLE:
        raise ImportError("Twisted is required for ssl_context_factory")
    
    factory = ssl.DefaultOpenSSLContextFactory(
        str(Path(__file__).parent.parent / keyfile),
        str(Path(__file__).parent.parent / certfile),
    )
    if cipher_string:
        ctx = factory.getContext()
        # disabling TLS1.3 because it unconditionally enables some strong ciphers
        ctx.set_options(SSL.OP_CIPHER_SERVER_PREFERENCE | SSL.OP_NO_TLSv1_3)
        ctx.set_cipher_list(to_bytes(cipher_string))
    return factory


def ssl_context_factory_aiohttp(
    keyfile="keys/localhost.key", certfile="keys/localhost.crt", cipher_string=None
):
    """Aiohttp-based SSL context factory."""
    key_path = Path(__file__).parent.parent / keyfile
    cert_path = Path(__file__).parent.parent / certfile
    
    ssl_context = stdlib_ssl.create_default_context(stdlib_ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(str(cert_path), str(key_path))
    
    if cipher_string:
        # Disable TLS 1.3 to match Twisted behavior
        ssl_context.maximum_version = stdlib_ssl.TLSVersion.TLSv1_2
        ssl_context.set_ciphers(cipher_string)
    
    return ssl_context
