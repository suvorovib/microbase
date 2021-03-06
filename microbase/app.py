import logging.config
import sys
from typing import List, Tuple, Callable, Sequence, Type, Union, ClassVar

import microbase
from microbase.config import GeneralConfig, BaseConfig
from microbase.logging_config import get_logging_config
from microbase.exception import ApplicationError, RouteError, log_uncaught
from microbase.route import Route
from microbase.endpoint import Endpoint, HealthEndpoint
from microbase.context import _context_mutable, context
from microbase.middleware import MiddlewareType

from sanic import Sanic, Blueprint
from sanic.config import Config
from sanic.exceptions import URLBuildError
from structlog import get_logger

from microbase_auth import AuthManager, AuthSignatureType

log = get_logger('microbase')


class Application(object):
    """
    App object
    """
    _server: Sanic
    _routes: List[Route]
    _hooks: List[Tuple]
    _middlewares: List[Tuple[MiddlewareType, Callable]]
    config: Config

    bp_prefix: str = ''

    def __init__(self, bp_prefix: str = None):
        self._init_config()
        self._init_logging()
        self._init_routes()
        self._init_hooks()
        self._init_middlewares()

        if bp_prefix is not None:
            self.bp_prefix = bp_prefix

    def _init_config(self):
        self.config = Config(load_env=True)
        self.config.from_object(GeneralConfig)

    def _init_logging(self):
        self._logging_config = get_logging_config(self.config)
        logging.config.dictConfig(self._logging_config)

    def _init_routes(self):
        self._routes = []

    def _init_hooks(self):
        self._hooks = []

    def _init_middlewares(self):
        self._middlewares = []

    def _apply_logging(self):
        self._logging_config = get_logging_config(self.config)
        logging.config.dictConfig(self._logging_config)

    def _apply_routes(self):
        self._routes.append(Route(HealthEndpoint(context), '/health'))

        if len(self.bp_prefix) == 0:
            [self._server.add_route(r.handler, r.uri, methods=r.methods, strict_slashes=r.strict_slashes, name=r.name) for r in self._routes]
        else:
            blueprint = Blueprint(self.bp_prefix, url_prefix=self.bp_prefix)

            [blueprint.add_route(r.handler, r.uri, methods=r.methods, strict_slashes=r.strict_slashes, name=r.name) for r in self._routes]
            self._server.register_blueprint(blueprint)

    def _apply_hooks(self):
        for hook_name, hook_handler in self._hooks:
            self._server.listener(hook_name.value)(hook_handler)

    def _apply_middlewares(self):
        for type, middleware in self._middlewares:
            self._server.middleware(type.value)(middleware)

    def _prepare_server(self):
        self._server = Sanic(__name__, log_config=self._logging_config)
        self._server.config = self.config
        # self._server.config.LOGO = self._server.config.LOGO and None
        self._apply_routes()
        self._apply_hooks()
        self._apply_middlewares()

        auth = AuthManager()
        auth.set_signature(self.config.USER_JWT_SIGNATURE, AuthSignatureType.User)
        auth.set_signature(self.config.SERVICE_JWT_SIGNATURE, AuthSignatureType.Service)

        self.add_to_context('auth', auth)

    def add_config(self, config_obj: ClassVar[BaseConfig]):
        """
        Add application config
        """
        self.config.from_object(config_obj)

    def add_route(self, route: ClassVar[Route]):
        """
        Add route
        """
        self._routes.append(route)

    def add_routes(self, routes: List[Route]):
        """
        Add routes
        """
        [self._routes.append(route) for route in routes]

    def add_server_hook(self, hook_name, handler):
        """
        Add hook
        """
        # cycling imports resolving
        from microbase.hook import HookNames, HookHandler

        if not isinstance(hook_name, HookNames):
            raise ApplicationError('Hook must be one of HookNames enum')
        hook_handler = HookHandler(self, handler)

        self._hooks.append((hook_name, hook_handler))

    def add_to_context(self, name, obj):
        """
        Add object to context.
        """
        _context_mutable.set(name, obj)

    def add_middleware(self, middleware_type: MiddlewareType, middleware: Callable):
        """
        Add middleware
        """
        if not isinstance(middleware_type, MiddlewareType):
            raise ApplicationError('middleware_type must be Middleware enum')

        if not callable(middleware):
            raise ApplicationError('middleware must be callable')

        self._middlewares.append((middleware_type, middleware))

    def run(self):
        self._apply_logging()
        self._prepare_server()

        self._server.run(host=self.config.APP_HOST, port=self.config.APP_PORT, debug=self.config.DEBUG, workers=self.config.WORKERS)


if __name__ == '__main__':
    a = Application()
    a.run()
