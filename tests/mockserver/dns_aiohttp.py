"""Asyncio-based DNS mock server for tests.

This replaces the Twisted-based DNS server with a pure asyncio implementation.
"""

from __future__ import annotations

import asyncio
import sys
from subprocess import PIPE, Popen

from tests.utils import get_script_run_env


class MockDNSServer:
    """Context manager for mock DNS server."""
    
    def __enter__(self):
        self.proc = Popen(
            [sys.executable, "-u", "-m", "tests.mockserver.dns_aiohttp"],
            stdout=PIPE,
            env=get_script_run_env(),
        )
        self.host = "127.0.0.1"
        self.port = int(
            self.proc.stdout.readline().strip().decode("ascii").split(":")[1]
        )
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.proc.kill()
        self.proc.communicate()


class DNSProtocol(asyncio.DatagramProtocol):
    """Simple DNS protocol for testing."""
    
    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        """Handle DNS query and send response."""
        # Simple DNS response implementation
        # For testing purposes, always respond with 127.0.0.1
        
        # Parse minimal DNS query (just get transaction ID)
        if len(data) < 12:
            return
        
        transaction_id = data[0:2]
        
        # Build DNS response
        # Header: transaction ID + flags (response, no error)
        flags = b'\x81\x80'  # Standard query response, no error
        qdcount = b'\x00\x01'  # 1 question
        ancount = b'\x00\x01'  # 1 answer
        nscount = b'\x00\x00'  # 0 authority records
        arcount = b'\x00\x00'  # 0 additional records
        
        header = transaction_id + flags + qdcount + ancount + nscount + arcount
        
        # Copy question section from query (after header)
        question = data[12:]
        
        # Find the end of the domain name (null byte) and add QTYPE and QCLASS
        null_index = question.find(b'\x00')
        if null_index == -1:
            return
        
        # Answer section: pointer to name in question, type A, class IN, TTL, length, IP
        answer_name = b'\xc0\x0c'  # Pointer to offset 12 (start of question)
        answer_type = b'\x00\x01'  # Type A
        answer_class = b'\x00\x01'  # Class IN
        answer_ttl = b'\x00\x00\x00\x3c'  # TTL 60 seconds
        answer_rdlength = b'\x00\x04'  # 4 bytes for IPv4
        answer_rdata = b'\x7f\x00\x00\x01'  # 127.0.0.1
        
        answer = (answer_name + answer_type + answer_class + answer_ttl + 
                 answer_rdlength + answer_rdata)
        
        response = header + question + answer
        
        self.transport.sendto(response, addr)


async def start_server(host='127.0.0.1', port=0):
    """Start DNS server on specified host and port."""
    loop = asyncio.get_event_loop()
    
    # Create UDP endpoint
    transport, protocol = await loop.create_datagram_endpoint(
        DNSProtocol,
        local_addr=(host, port)
    )
    
    # Get actual port if port was 0
    sock = transport.get_extra_info('socket')
    actual_port = sock.getsockname()[1]
    
    return transport, actual_port


def main() -> None:
    """Main entry point for DNS server."""
    async def run():
        transport, port = await start_server()
        print(f"127.0.0.1:{port}")
        sys.stdout.flush()
        
        # Run forever
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            transport.close()
    
    asyncio.run(run())


if __name__ == "__main__":
    main()
