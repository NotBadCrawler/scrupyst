import logging
import ssl
from typing import Any

logger = logging.getLogger(__name__)


METHOD_TLS = "TLS"
METHOD_TLSv10 = "TLSv1.0"
METHOD_TLSv11 = "TLSv1.1"
METHOD_TLSv12 = "TLSv1.2"
METHOD_TLSv13 = "TLSv1.3"


# Mapping of TLS method names to ssl module protocol constants
TLS_METHOD_NAMES: dict[str, str] = {
    METHOD_TLS: METHOD_TLS,  # Auto-negotiate (recommended)
    METHOD_TLSv10: METHOD_TLSv10,  # TLS 1.0 only (deprecated)
    METHOD_TLSv11: METHOD_TLSv11,  # TLS 1.1 only (deprecated)
    METHOD_TLSv12: METHOD_TLSv12,  # TLS 1.2 only
    METHOD_TLSv13: METHOD_TLSv13,  # TLS 1.3 only
}


DEFAULT_CIPHERS: str = "DEFAULT"


def get_ssl_context(
    method: str = METHOD_TLS,
    verify_mode: ssl.VerifyMode = ssl.CERT_NONE,
    ciphers: str | None = None,
    check_hostname: bool = False,
    load_default_certs: bool = False,
) -> ssl.SSLContext:
    """
    Create an SSL context for HTTPS connections.

    Args:
        method: TLS method/version to use
        verify_mode: Certificate verification mode
        ciphers: Cipher suite string
        check_hostname: Whether to check hostname against certificate
        load_default_certs: Whether to load system's default CA certificates

    Returns:
        Configured ssl.SSLContext
    """
    # Create SSL context with appropriate protocol
    # Use PROTOCOL_TLS_CLIENT for client connections (auto-negotiates version)
    if method == METHOD_TLS:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    else:
        # For specific TLS versions, we still use PROTOCOL_TLS_CLIENT
        # and configure minimum/maximum versions
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        
        # Map method names to ssl module constants for version control
        if method == METHOD_TLSv10:
            ctx.minimum_version = ssl.TLSVersion.TLSv1
            ctx.maximum_version = ssl.TLSVersion.TLSv1
        elif method == METHOD_TLSv11:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_1
            ctx.maximum_version = ssl.TLSVersion.TLSv1_1
        elif method == METHOD_TLSv12:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        elif method == METHOD_TLSv13:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_3
            ctx.maximum_version = ssl.TLSVersion.TLSv1_3

    # Set verification mode
    ctx.check_hostname = check_hostname
    ctx.verify_mode = verify_mode

    # Load default CA certificates if requested
    if load_default_certs:
        ctx.load_default_certs()

    # Set ciphers if specified
    if ciphers:
        try:
            ctx.set_ciphers(ciphers)
        except ssl.SSLError as e:
            logger.warning(f"Failed to set ciphers '{ciphers}': {e}")

    # Enable legacy server connect option for better compatibility
    # This is equivalent to OpenSSL's OP_LEGACY_SERVER_CONNECT
    try:
        ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT  # type: ignore[attr-defined]
    except AttributeError:
        # OP_LEGACY_SERVER_CONNECT might not be available
        pass

    return ctx
