from app.errors.page import Page as ErrorsPage
from app.fetch.page import FetchPage
from app.flow.page import Page as FlowPage
from app.forms.page import FormsPage
from app.holes.page import Page as HolesPage
from app.page import Page as HomePage
from app.patterns.page import Page as PatternsPage
from app.primitives.page import Page as PrimitivesPage
from app.stores.page import Page as StoresPage
from wybthon import Route, lazy, load_component


def _AboutLazy():
    return ("app.about.page", "Page")


def _TeamLazy():
    return ("app.about.team.page", "Page")


Docs = load_component("app.docs.page", "Page")


def create_routes():
    return [
        Route(path="/", component=lambda p: HomePage(p)),
        Route(
            path="/about",
            component=lazy(_AboutLazy),
            children=[
                Route(path="team", component=lazy(_TeamLazy)),
            ],
        ),
        Route(path="/fetch", component=lambda p: FetchPage(p)),
        Route(path="/flow", component=lambda p: FlowPage(p)),
        Route(path="/forms", component=lambda p: FormsPage(p)),
        Route(path="/errors", component=lambda p: ErrorsPage(p)),
        Route(path="/holes", component=lambda p: HolesPage(p)),
        Route(path="/patterns", component=lambda p: PatternsPage(p)),
        Route(path="/primitives", component=lambda p: PrimitivesPage(p)),
        Route(path="/stores", component=lambda p: StoresPage(p)),
        Route(path="/docs/*", component=Docs),
    ]
