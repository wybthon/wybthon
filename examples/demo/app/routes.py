from app.errors.page import Page as ErrorsPage
from app.fetch.page import FetchPage
from app.flow.page import Page as FlowPage
from app.forms.page import FormsPage
from app.holes.page import Page as HolesPage
from app.page import Page as HomePage
from app.patterns.page import Page as PatternsPage
from app.primitives.page import Page as PrimitivesPage
from app.props.page import Page as PropsPage
from app.stores.page import Page as StoresPage
from wybthon import Route, lazy, load_component


def _AboutLazy():
    return ("app.about.page", "Page")


def _TeamLazy():
    return ("app.about.team.page", "Page")


Docs = load_component("app.docs.page", "Page")


def create_routes():
    return [
        Route(path="/", component=HomePage),
        Route(
            path="/about",
            component=lazy(_AboutLazy),
            children=[
                Route(path="team", component=lazy(_TeamLazy)),
            ],
        ),
        Route(path="/fetch", component=FetchPage),
        Route(path="/flow", component=FlowPage),
        Route(path="/forms", component=FormsPage),
        Route(path="/errors", component=ErrorsPage),
        Route(path="/holes", component=HolesPage),
        Route(path="/patterns", component=PatternsPage),
        Route(path="/primitives", component=PrimitivesPage),
        Route(path="/props", component=PropsPage),
        Route(path="/stores", component=StoresPage),
        Route(path="/docs/*", component=Docs),
    ]
