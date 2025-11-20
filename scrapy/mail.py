"""
Mail sending helpers

See documentation in docs/topics/email.rst
"""

from __future__ import annotations

import asyncio
import logging
import ssl as ssl_module
from email import encoders as Encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.nonmultipart import MIMENonMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from io import BytesIO
from typing import IO, TYPE_CHECKING, Any

from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import to_bytes

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler


logger = logging.getLogger(__name__)


# Defined in the email.utils module, but undocumented:
# https://github.com/python/cpython/blob/v3.9.0/Lib/email/utils.py#L42
COMMASPACE = ", "


def _to_bytes_or_none(text: str | bytes | None) -> bytes | None:
    if text is None:
        return None
    return to_bytes(text)


class MailSender:
    def __init__(
        self,
        smtphost: str = "localhost",
        mailfrom: str = "scrapy@localhost",
        smtpuser: str | None = None,
        smtppass: str | None = None,
        smtpport: int = 25,
        smtptls: bool = False,
        smtpssl: bool = False,
        debug: bool = False,
    ):
        self.smtphost: str = smtphost
        self.smtpport: int = smtpport
        self.smtpuser: bytes | None = _to_bytes_or_none(smtpuser)
        self.smtppass: bytes | None = _to_bytes_or_none(smtppass)
        self.smtptls: bool = smtptls
        self.smtpssl: bool = smtpssl
        self.mailfrom: str = mailfrom
        self.debug: bool = debug

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        settings = crawler.settings
        return cls(
            smtphost=settings["MAIL_HOST"],
            mailfrom=settings["MAIL_FROM"],
            smtpuser=settings["MAIL_USER"],
            smtppass=settings["MAIL_PASS"],
            smtpport=settings.getint("MAIL_PORT"),
            smtptls=settings.getbool("MAIL_TLS"),
            smtpssl=settings.getbool("MAIL_SSL"),
        )

    def send(
        self,
        to: str | list[str],
        subject: str,
        body: str,
        cc: str | list[str] | None = None,
        attachs: Sequence[tuple[str, str, IO[Any]]] = (),
        mimetype: str = "text/plain",
        charset: str | None = None,
        _callback: Callable[..., None] | None = None,
    ) -> asyncio.Future[None] | None:
        msg: MIMEBase = (
            MIMEMultipart() if attachs else MIMENonMultipart(*mimetype.split("/", 1))
        )

        to = list(arg_to_iter(to))
        cc = list(arg_to_iter(cc))

        msg["From"] = self.mailfrom
        msg["To"] = COMMASPACE.join(to)
        msg["Date"] = formatdate(localtime=True)
        msg["Subject"] = subject
        rcpts = to[:]
        if cc:
            rcpts.extend(cc)
            msg["Cc"] = COMMASPACE.join(cc)

        if attachs:
            if charset:
                msg.set_charset(charset)
            msg.attach(MIMEText(body, "plain", charset or "us-ascii"))
            for attach_name, attach_mimetype, f in attachs:
                part = MIMEBase(*attach_mimetype.split("/"))
                part.set_payload(f.read())
                Encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition", "attachment", filename=attach_name
                )
                msg.attach(part)
        else:
            msg.set_payload(body, charset)

        if _callback:
            _callback(to=to, subject=subject, body=body, cc=cc, attach=attachs, msg=msg)

        if self.debug:
            logger.debug(
                "Debug mail sent OK: To=%(mailto)s Cc=%(mailcc)s "
                'Subject="%(mailsubject)s" Attachs=%(mailattachs)d',
                {
                    "mailto": to,
                    "mailcc": cc,
                    "mailsubject": subject,
                    "mailattachs": len(attachs),
                },
            )
            return None

        future = asyncio.ensure_future(
            self._sendmail_async(rcpts, msg.as_string().encode(charset or "utf-8"))
        )
        
        def _handle_result(fut: asyncio.Future[None]) -> None:
            try:
                fut.result()
                self._sent_ok(None, to, cc, subject, len(attachs))
            except Exception as e:
                self._sent_failed(e, to, cc, subject, len(attachs))
        
        future.add_done_callback(_handle_result)
        return future

    def _sent_ok(
        self, result: Any, to: list[str], cc: list[str], subject: str, nattachs: int
    ) -> None:
        logger.info(
            "Mail sent OK: To=%(mailto)s Cc=%(mailcc)s "
            'Subject="%(mailsubject)s" Attachs=%(mailattachs)d',
            {
                "mailto": to,
                "mailcc": cc,
                "mailsubject": subject,
                "mailattachs": nattachs,
            },
        )

    def _sent_failed(
        self,
        error: Exception,
        to: list[str],
        cc: list[str],
        subject: str,
        nattachs: int,
    ) -> None:
        errstr = str(error)
        logger.error(
            "Unable to send mail: To=%(mailto)s Cc=%(mailcc)s "
            'Subject="%(mailsubject)s" Attachs=%(mailattachs)d'
            "- %(mailerr)s",
            {
                "mailto": to,
                "mailcc": cc,
                "mailsubject": subject,
                "mailattachs": nattachs,
                "mailerr": errstr,
            },
        )

    async def _sendmail_async(self, to_addrs: list[str], msg: bytes) -> None:
        """Send email using aiosmtplib or stdlib smtplib via executor."""
        try:
            # Try using aiosmtplib if available
            import aiosmtplib  # noqa: PLC0415

            smtp_kwargs = {
                "hostname": self.smtphost,
                "port": self.smtpport,
                "use_tls": self.smtpssl,
                "start_tls": self.smtptls and not self.smtpssl,
            }
            
            if self.smtpuser and self.smtppass:
                smtp_kwargs["username"] = self.smtpuser.decode("utf-8")
                smtp_kwargs["password"] = self.smtppass.decode("utf-8")

            await aiosmtplib.send(
                msg,
                sender=self.mailfrom,
                recipients=to_addrs,
                **smtp_kwargs,
            )
        except ImportError:
            # Fall back to using stdlib smtplib in executor
            import smtplib  # noqa: PLC0415
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._sendmail_sync(to_addrs, msg, smtplib),
            )

    def _sendmail_sync(
        self, to_addrs: list[str], msg: bytes, smtplib: Any
    ) -> None:
        """Synchronous fallback using stdlib smtplib."""
        smtp_cls = smtplib.SMTP_SSL if self.smtpssl else smtplib.SMTP
        
        with smtp_cls(self.smtphost, self.smtpport) as smtp:
            if self.smtptls and not self.smtpssl:
                context = ssl_module.create_default_context()
                smtp.starttls(context=context)
            
            if self.smtpuser and self.smtppass:
                smtp.login(
                    self.smtpuser.decode("utf-8"),
                    self.smtppass.decode("utf-8"),
                )
            
            smtp.sendmail(self.mailfrom, to_addrs, msg)
