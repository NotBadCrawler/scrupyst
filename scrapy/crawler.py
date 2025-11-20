from __future__ import annotations

import asyncio
import contextlib
import logging
import pprint
import signal
import warnings
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, TypeVar

from scrapy import Spider
from scrapy.addons import AddonManager
from scrapy.core.engine import ExecutionEngine
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.extension import ExtensionManager
from scrapy.settings import Settings, overridden_settings
from scrapy.signalmanager import SignalManager
from scrapy.spiderloader import SpiderLoaderProtocol, get_spider_loader
from scrapy.utils.asyncio import is_asyncio_available
from scrapy.utils.log import (
    configure_logging,
    get_scrapy_root_handler,
    install_scrapy_root_handler,
    log_reactor_info,
    log_scrapy_info,
)
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.ossignal import install_shutdown_handlers, signal_names
from scrapy.utils.reactor import (
    _asyncio_reactor_path,
    install_reactor,
    is_asyncio_reactor_installed,
    is_reactor_installed,
    verify_installed_asyncio_event_loop,
    verify_installed_reactor,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Iterable

    from scrapy.logformatter import LogFormatter
    from scrapy.statscollectors import StatsCollector
    from scrapy.utils.request import RequestFingerprinterProtocol


logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class Crawler:
    def __init__(
        self,
        spidercls: type[Spider],
        settings: dict[str, Any] | Settings | None = None,
        init_reactor: bool = False,
    ):
        if isinstance(spidercls, Spider):
            raise ValueError("The spidercls argument must be a class, not an object")

        if isinstance(settings, dict) or settings is None:
            settings = Settings(settings)

        self.spidercls: type[Spider] = spidercls
        self.settings: Settings = settings.copy()
        self.spidercls.update_settings(self.settings)
        self._update_root_log_handler()

        self.addons: AddonManager = AddonManager(self)
        self.signals: SignalManager = SignalManager(self)

        self._init_reactor: bool = init_reactor
        self.crawling: bool = False
        self._started: bool = False

        self.extensions: ExtensionManager | None = None
        self.stats: StatsCollector | None = None
        self.logformatter: LogFormatter | None = None
        self.request_fingerprinter: RequestFingerprinterProtocol | None = None
        self.spider: Spider | None = None
        self.engine: ExecutionEngine | None = None

    def _update_root_log_handler(self) -> None:
        if get_scrapy_root_handler() is not None:
            # scrapy root handler already installed: update it with new settings
            install_scrapy_root_handler(self.settings)

    def _apply_settings(self) -> None:
        if self.settings.frozen:
            return

        self.addons.load_settings(self.settings)
        self.stats = load_object(self.settings["STATS_CLASS"])(self)

        lf_cls: type[LogFormatter] = load_object(self.settings["LOG_FORMATTER"])
        self.logformatter = lf_cls.from_crawler(self)

        self.request_fingerprinter = build_from_crawler(
            load_object(self.settings["REQUEST_FINGERPRINTER_CLASS"]),
            self,
        )

        reactor_class: str = self.settings["TWISTED_REACTOR"]
        event_loop: str = self.settings["ASYNCIO_EVENT_LOOP"]
        # this needs to be done after the spider settings are merged
        if self._init_reactor and reactor_class:
            install_reactor(reactor_class, event_loop)
            # Reactor is no longer needed with pure asyncio,
            # but we keep the install_reactor call for backward compatibility
        if reactor_class:
            verify_installed_reactor(reactor_class)
            if is_asyncio_reactor_installed() and event_loop:
                verify_installed_asyncio_event_loop(event_loop)

        if self._init_reactor or reactor_class:
            log_reactor_info()

        self.extensions = ExtensionManager.from_crawler(self)
        self.settings.freeze()

        d = dict(overridden_settings(self.settings))
        logger.info(
            "Overridden settings:\n%(settings)s", {"settings": pprint.pformat(d)}
        )

    # Deprecated wrapper for backward compatibility
    def crawl(self, *args: Any, **kwargs: Any) -> asyncio.Task[None]:
        """Start the crawler by instantiating its spider class with the given
        *args* and *kwargs* arguments, while setting the execution engine in
        motion. Should be called only once.

        .. deprecated:: VERSION
            Use :meth:`crawl_async` instead.

        Return a task that completes when the crawl is finished.
        """
        warnings.warn(
            "Crawler.crawl() is deprecated, use crawl_async() instead",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return asyncio.create_task(self.crawl_async(*args, **kwargs))

    async def crawl_async(self, *args: Any, **kwargs: Any) -> None:
        """Start the crawler by instantiating its spider class with the given
        *args* and *kwargs* arguments, while setting the execution engine in
        motion. Should be called only once.

        .. versionadded:: VERSION

        Complete when the crawl is finished.

        This function requires asyncio to be available.
        """
        if not is_asyncio_available():
            raise RuntimeError("Crawler.crawl_async() requires asyncio.")
        if self.crawling:
            raise RuntimeError("Crawling already taking place")
        if self._started:
            raise RuntimeError(
                "Cannot run Crawler.crawl_async() more than once on the same instance."
            )
        self.crawling = self._started = True

        try:
            self.spider = self._create_spider(*args, **kwargs)
            self._apply_settings()
            self._update_root_log_handler()
            self.engine = self._create_engine()
            await self.engine.open_spider_async()
            await self.engine.start_async()
        except Exception:
            self.crawling = False
            if self.engine is not None:
                await self.engine.close_async()
            raise

    def _create_spider(self, *args: Any, **kwargs: Any) -> Spider:
        return self.spidercls.from_crawler(self, *args, **kwargs)

    def _create_engine(self) -> ExecutionEngine:
        return ExecutionEngine(self, lambda _: self.stop_async())

    def stop(self) -> asyncio.Task[None]:
        """Start a graceful stop of the crawler and return a task that completes
        when the crawler is stopped.

        .. deprecated:: VERSION
            Use :meth:`stop_async` instead.
        """
        warnings.warn(
            "Crawler.stop() is deprecated, use stop_async() instead",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return asyncio.create_task(self.stop_async())

    async def stop_async(self) -> None:
        """Start a graceful stop of the crawler and complete when the crawler is stopped.

        .. versionadded:: VERSION
        """
        if self.crawling:
            self.crawling = False
            assert self.engine
            if self.engine.running:
                await self.engine.stop_async()

    @staticmethod
    def _get_component(
        component_class: type[_T], components: Iterable[Any]
    ) -> _T | None:
        for component in components:
            if isinstance(component, component_class):
                return component
        return None

    def get_addon(self, cls: type[_T]) -> _T | None:
        """Return the run-time instance of an :ref:`add-on <topics-addons>` of
        the specified class or a subclass, or ``None`` if none is found.

        .. versionadded:: 2.12
        """
        return self._get_component(cls, self.addons.addons)

    def get_downloader_middleware(self, cls: type[_T]) -> _T | None:
        """Return the run-time instance of a :ref:`downloader middleware
        <topics-downloader-middleware>` of the specified class or a subclass,
        or ``None`` if none is found.

        .. versionadded:: 2.12

        This method can only be called after the crawl engine has been created,
        e.g. at signals :signal:`engine_started` or :signal:`spider_opened`.
        """
        if not self.engine:
            raise RuntimeError(
                "Crawler.get_downloader_middleware() can only be called after "
                "the crawl engine has been created."
            )
        return self._get_component(cls, self.engine.downloader.middleware.middlewares)

    def get_extension(self, cls: type[_T]) -> _T | None:
        """Return the run-time instance of an :ref:`extension
        <topics-extensions>` of the specified class or a subclass,
        or ``None`` if none is found.

        .. versionadded:: 2.12

        This method can only be called after the extension manager has been
        created, e.g. at signals :signal:`engine_started` or
        :signal:`spider_opened`.
        """
        if not self.extensions:
            raise RuntimeError(
                "Crawler.get_extension() can only be called after the "
                "extension manager has been created."
            )
        return self._get_component(cls, self.extensions.middlewares)

    def get_item_pipeline(self, cls: type[_T]) -> _T | None:
        """Return the run-time instance of a :ref:`item pipeline
        <topics-item-pipeline>` of the specified class or a subclass, or
        ``None`` if none is found.

        .. versionadded:: 2.12

        This method can only be called after the crawl engine has been created,
        e.g. at signals :signal:`engine_started` or :signal:`spider_opened`.
        """
        if not self.engine:
            raise RuntimeError(
                "Crawler.get_item_pipeline() can only be called after the "
                "crawl engine has been created."
            )
        return self._get_component(cls, self.engine.scraper.itemproc.middlewares)

    def get_spider_middleware(self, cls: type[_T]) -> _T | None:
        """Return the run-time instance of a :ref:`spider middleware
        <topics-spider-middleware>` of the specified class or a subclass, or
        ``None`` if none is found.

        .. versionadded:: 2.12

        This method can only be called after the crawl engine has been created,
        e.g. at signals :signal:`engine_started` or :signal:`spider_opened`.
        """
        if not self.engine:
            raise RuntimeError(
                "Crawler.get_spider_middleware() can only be called after the "
                "crawl engine has been created."
            )
        return self._get_component(cls, self.engine.scraper.spidermw.middlewares)


class CrawlerRunnerBase(ABC):
    def __init__(self, settings: dict[str, Any] | Settings | None = None):
        if isinstance(settings, dict) or settings is None:
            settings = Settings(settings)
        AddonManager.load_pre_crawler_settings(settings)
        self.settings: Settings = settings
        self.spider_loader: SpiderLoaderProtocol = get_spider_loader(settings)
        self._crawlers: set[Crawler] = set()
        self.bootstrap_failed = False

    @property
    def crawlers(self) -> set[Crawler]:
        """Set of :class:`crawlers <scrapy.crawler.Crawler>` started by
        :meth:`crawl` and managed by this class."""
        return self._crawlers

    def create_crawler(
        self, crawler_or_spidercls: type[Spider] | str | Crawler
    ) -> Crawler:
        """
        Return a :class:`~scrapy.crawler.Crawler` object.

        * If ``crawler_or_spidercls`` is a Crawler, it is returned as-is.
        * If ``crawler_or_spidercls`` is a Spider subclass, a new Crawler
          is constructed for it.
        * If ``crawler_or_spidercls`` is a string, this function finds
          a spider with this name in a Scrapy project (using spider loader),
          then creates a Crawler instance for it.
        """
        if isinstance(crawler_or_spidercls, Spider):
            raise ValueError(
                "The crawler_or_spidercls argument cannot be a spider object, "
                "it must be a spider class (or a Crawler object)"
            )
        if isinstance(crawler_or_spidercls, Crawler):
            return crawler_or_spidercls
        return self._create_crawler(crawler_or_spidercls)

    def _create_crawler(self, spidercls: str | type[Spider]) -> Crawler:
        if isinstance(spidercls, str):
            spidercls = self.spider_loader.load(spidercls)
        return Crawler(spidercls, self.settings)

    @abstractmethod
    def crawl(
        self,
        crawler_or_spidercls: type[Spider] | str | Crawler,
        *args: Any,
        **kwargs: Any,
    ) -> Awaitable[None]:
        raise NotImplementedError


class CrawlerRunner(CrawlerRunnerBase):
    """
    This is a convenient helper class that keeps track of, manages and runs
    crawlers.

    The CrawlerRunner object must be instantiated with a
    :class:`~scrapy.settings.Settings` object.

    This class shouldn't be needed (since Scrapy is responsible of using it
    accordingly) unless writing scripts that manually handle the crawling
    process. See :ref:`run-from-script` for an example.

    .. deprecated:: VERSION
        This class is deprecated. Use :class:`AsyncCrawlerRunner` instead.
        This class now provides asyncio.Task-based APIs for backward compatibility.
    """

    def __init__(self, settings: dict[str, Any] | Settings | None = None):
        super().__init__(settings)
        self._active: set[asyncio.Task[None]] = set()

    def crawl(
        self,
        crawler_or_spidercls: type[Spider] | str | Crawler,
        *args: Any,
        **kwargs: Any,
    ) -> asyncio.Task[None]:
        """
        Run a crawler with the provided arguments.

        It will call the given Crawler's :meth:`~Crawler.crawl` method, while
        keeping track of it so it can be stopped later.

        If ``crawler_or_spidercls`` isn't a :class:`~scrapy.crawler.Crawler`
        instance, this method will try to create one using this parameter as
        the spider class given to it.

        Returns a task that completes when the crawling is finished.

        :param crawler_or_spidercls: already created crawler, or a spider class
            or spider's name inside the project to create it
        :type crawler_or_spidercls: :class:`~scrapy.crawler.Crawler` instance,
            :class:`~scrapy.spiders.Spider` subclass or string

        :param args: arguments to initialize the spider

        :param kwargs: keyword arguments to initialize the spider
        """
        if isinstance(crawler_or_spidercls, Spider):
            raise ValueError(
                "The crawler_or_spidercls argument cannot be a spider object, "
                "it must be a spider class (or a Crawler object)"
            )
        crawler = self.create_crawler(crawler_or_spidercls)
        return self._crawl(crawler, *args, **kwargs)

    def _crawl(self, crawler: Crawler, *args: Any, **kwargs: Any) -> asyncio.Task[None]:
        self.crawlers.add(crawler)
        loop = asyncio.get_event_loop()
        task = loop.create_task(crawler.crawl_async(*args, **kwargs))
        self._active.add(task)

        def _done(_: asyncio.Task[None]) -> None:
            self.crawlers.discard(crawler)
            self._active.discard(task)
            self.bootstrap_failed |= not getattr(crawler, "spider", None)

        task.add_done_callback(_done)
        return task

    async def stop(self) -> None:
        """
        Stops simultaneously all the crawling jobs taking place.

        Completes when they all have ended.
        """
        if self.crawlers:
            await asyncio.wait(
                [asyncio.create_task(c.stop_async()) for c in self.crawlers]
            )

    async def join(self) -> None:
        """
        Completes when all managed :attr:`crawlers` have completed their
        executions.
        """
        while self._active:
            await asyncio.wait(self._active)


class AsyncCrawlerRunner(CrawlerRunnerBase):
    """
    This is a convenient helper class that keeps track of, manages and runs
    crawlers.

    The AsyncCrawlerRunner object must be instantiated with a
    :class:`~scrapy.settings.Settings` object.

    This class shouldn't be needed (since Scrapy is responsible of using it
    accordingly) unless writing scripts that manually handle the crawling
    process. See :ref:`run-from-script` for an example.

    This class provides coroutine APIs and requires asyncio.
    """

    def __init__(self, settings: dict[str, Any] | Settings | None = None):
        super().__init__(settings)
        self._active: set[asyncio.Task[None]] = set()

    def crawl(
        self,
        crawler_or_spidercls: type[Spider] | str | Crawler,
        *args: Any,
        **kwargs: Any,
    ) -> asyncio.Task[None]:
        """
        Run a crawler with the provided arguments.

        It will call the given Crawler's :meth:`~Crawler.crawl` method, while
        keeping track of it so it can be stopped later.

        If ``crawler_or_spidercls`` isn't a :class:`~scrapy.crawler.Crawler`
        instance, this method will try to create one using this parameter as
        the spider class given to it.

        Returns a :class:`~asyncio.Task` object which completes when the
        crawling is finished.

        :param crawler_or_spidercls: already created crawler, or a spider class
            or spider's name inside the project to create it
        :type crawler_or_spidercls: :class:`~scrapy.crawler.Crawler` instance,
            :class:`~scrapy.spiders.Spider` subclass or string

        :param args: arguments to initialize the spider

        :param kwargs: keyword arguments to initialize the spider
        """
        if isinstance(crawler_or_spidercls, Spider):
            raise ValueError(
                "The crawler_or_spidercls argument cannot be a spider object, "
                "it must be a spider class (or a Crawler object)"
            )
        if not is_asyncio_reactor_installed():
            raise RuntimeError(
                f"{type(self).__name__} requires asyncio event loop to be installed."
            )
        crawler = self.create_crawler(crawler_or_spidercls)
        return self._crawl(crawler, *args, **kwargs)

    def _crawl(self, crawler: Crawler, *args: Any, **kwargs: Any) -> asyncio.Task[None]:
        # At this point the asyncio loop has been installed either by the user
        # or by AsyncCrawlerProcess (but it isn't running yet, so no asyncio.create_task()).
        loop = asyncio.get_event_loop()
        self.crawlers.add(crawler)
        task = loop.create_task(crawler.crawl_async(*args, **kwargs))
        self._active.add(task)

        def _done(_: asyncio.Task[None]) -> None:
            self.crawlers.discard(crawler)
            self._active.discard(task)
            self.bootstrap_failed |= not getattr(crawler, "spider", None)

        task.add_done_callback(_done)
        return task

    async def stop(self) -> None:
        """
        Stops simultaneously all the crawling jobs taking place.

        Completes when they all have ended.
        """
        if self.crawlers:
            await asyncio.wait(
                [asyncio.create_task(c.stop_async()) for c in self.crawlers]
            )

    async def join(self) -> None:
        """
        Completes when all managed :attr:`crawlers` have completed their
        executions.
        """
        while self._active:
            await asyncio.wait(self._active)


class CrawlerProcessBase(CrawlerRunnerBase):
    def __init__(
        self,
        settings: dict[str, Any] | Settings | None = None,
        install_root_handler: bool = True,
    ):
        super().__init__(settings)
        configure_logging(self.settings, install_root_handler)
        log_scrapy_info(self.settings)

    @abstractmethod
    def start(
        self, stop_after_crawl: bool = True, install_signal_handlers: bool = True
    ) -> None:
        raise NotImplementedError

    def _signal_shutdown(self, signum: int, _: Any) -> None:
        loop = asyncio.get_event_loop()
        install_shutdown_handlers(self._signal_kill)
        signame = signal_names[signum]
        logger.info(
            "Received %(signame)s, shutting down gracefully. Send again to force ",
            {"signame": signame},
        )
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self._graceful_stop_loop())
        )

    def _signal_kill(self, signum: int, _: Any) -> None:
        loop = asyncio.get_event_loop()
        install_shutdown_handlers(signal.SIG_IGN)
        signame = signal_names[signum]
        logger.info(
            "Received %(signame)s twice, forcing unclean shutdown", {"signame": signame}
        )
        loop.call_soon_threadsafe(self._stop_loop)

    def _setup_event_loop(self, install_signal_handlers_flag: bool) -> None:
        loop = asyncio.get_event_loop()

        resolver_class = load_object(self.settings["DNS_RESOLVER"])
        # We pass self, which is CrawlerProcess, instead of Crawler here,
        # which works because the default resolvers only use crawler.settings.
        # Note: DNS resolver may need asyncio adaptation
        resolver = build_from_crawler(resolver_class, self)  # type: ignore[arg-type]
        if hasattr(resolver, "install_on_reactor"):
            # For backward compatibility with resolvers that expect reactor
            resolver.install_on_reactor()

        # Note: Thread pool management in asyncio is different from Twisted
        # The default executor can be configured if needed

        if install_signal_handlers_flag:
            # Install signal handlers when loop starts
            loop.call_soon(install_shutdown_handlers, self._signal_shutdown)

    @abstractmethod
    async def _stop_task(self) -> None:
        raise NotImplementedError

    async def _graceful_stop_loop(self) -> None:
        try:
            await self._stop_task()
        finally:
            self._stop_loop()

    def _stop_loop(self, _: Any = None) -> None:
        loop = asyncio.get_event_loop()
        # raised if already stopped or in shutdown stage
        with contextlib.suppress(RuntimeError):
            loop.stop()


class CrawlerProcess(CrawlerProcessBase, CrawlerRunner):
    """
    A class to run multiple scrapy crawlers in a process simultaneously.

    This class extends :class:`~scrapy.crawler.CrawlerRunner` by adding support
    for starting an asyncio event loop and handling shutdown signals, like the
    keyboard interrupt command Ctrl-C. It also configures top-level logging.

    This utility should be a better fit than
    :class:`~scrapy.crawler.CrawlerRunner` if you aren't running another
    asyncio event loop within your application.

    The CrawlerProcess object must be instantiated with a
    :class:`~scrapy.settings.Settings` object.

    :param install_root_handler: whether to install root logging handler
        (default: True)

    This class shouldn't be needed (since Scrapy is responsible of using it
    accordingly) unless writing scripts that manually handle the crawling
    process. See :ref:`run-from-script` for an example.

    .. deprecated:: VERSION
        This class is deprecated. Use :class:`AsyncCrawlerProcess` instead.
        This class now provides asyncio-based APIs for backward compatibility.
    """

    def __init__(
        self,
        settings: dict[str, Any] | Settings | None = None,
        install_root_handler: bool = True,
    ):
        super().__init__(settings, install_root_handler)
        self._initialized_reactor: bool = False
        logger.debug("Using CrawlerProcess")

    def _create_crawler(self, spidercls: type[Spider] | str) -> Crawler:
        if isinstance(spidercls, str):
            spidercls = self.spider_loader.load(spidercls)
        init_reactor = not self._initialized_reactor
        self._initialized_reactor = True
        return Crawler(spidercls, self.settings, init_reactor=init_reactor)

    async def _stop_task(self) -> None:
        await self.stop()

    def start(
        self, stop_after_crawl: bool = True, install_signal_handlers: bool = True
    ) -> None:
        """
        This method starts an asyncio event loop and installs a DNS cache
        based on :setting:`DNSCACHE_ENABLED` and :setting:`DNSCACHE_SIZE`.

        If ``stop_after_crawl`` is True, the event loop will be stopped after all
        crawlers have finished, using :meth:`join`.

        :param bool stop_after_crawl: stop or not the event loop when all
            crawlers have finished

        :param bool install_signal_handlers: whether to install the OS signal
            handlers (default: True)
        """
        loop = asyncio.get_event_loop()

        if stop_after_crawl:
            join_task = loop.create_task(self.join())
            join_task.add_done_callback(self._stop_loop)

        self._setup_event_loop(install_signal_handlers)
        loop.run_forever()  # blocking call


class AsyncCrawlerProcess(CrawlerProcessBase, AsyncCrawlerRunner):
    """
    A class to run multiple scrapy crawlers in a process simultaneously.

    This class extends :class:`~scrapy.crawler.AsyncCrawlerRunner` by adding support
    for starting an asyncio event loop and handling shutdown signals, like the
    keyboard interrupt command Ctrl-C. It also configures top-level logging.

    This utility should be a better fit than
    :class:`~scrapy.crawler.AsyncCrawlerRunner` if you aren't running another
    asyncio event loop within your application.

    The AsyncCrawlerProcess object must be instantiated with a
    :class:`~scrapy.settings.Settings` object.

    :param install_root_handler: whether to install root logging handler
        (default: True)

    This class shouldn't be needed (since Scrapy is responsible of using it
    accordingly) unless writing scripts that manually handle the crawling
    process. See :ref:`run-from-script` for an example.

    This class provides coroutine APIs and requires asyncio.
    """

    def __init__(
        self,
        settings: dict[str, Any] | Settings | None = None,
        install_root_handler: bool = True,
    ):
        super().__init__(settings, install_root_handler)
        logger.debug("Using AsyncCrawlerProcess")
        # We want the asyncio event loop to be installed early, so that it's
        # always the correct one.
        # The ASYNCIO_EVENT_LOOP setting cannot be overridden by add-ons and
        # spiders when using AsyncCrawlerProcess.
        loop_path = self.settings["ASYNCIO_EVENT_LOOP"]
        if is_reactor_installed():
            # The user could install a reactor before this class is instantiated.
            # We need to make sure the reactor is the correct one and the loop
            # type matches the setting.
            verify_installed_reactor(_asyncio_reactor_path)
            if loop_path:
                verify_installed_asyncio_event_loop(loop_path)
        else:
            install_reactor(_asyncio_reactor_path, loop_path)
        self._initialized_reactor = True

    async def _stop_task(self) -> None:
        await self.stop()

    def start(
        self, stop_after_crawl: bool = True, install_signal_handlers: bool = True
    ) -> None:
        """
        This method starts an asyncio event loop and installs a DNS cache
        based on :setting:`DNSCACHE_ENABLED` and :setting:`DNSCACHE_SIZE`.

        If ``stop_after_crawl`` is True, the event loop will be stopped after all
        crawlers have finished, using :meth:`join`.

        :param bool stop_after_crawl: stop or not the event loop when all
            crawlers have finished

        :param bool install_signal_handlers: whether to install the OS signal
            handlers (default: True)
        """
        loop = asyncio.get_event_loop()

        if stop_after_crawl:
            join_task = loop.create_task(self.join())
            join_task.add_done_callback(self._stop_loop)

        self._setup_event_loop(install_signal_handlers)
        loop.run_forever()  # blocking call
