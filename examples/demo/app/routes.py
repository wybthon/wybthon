from app.errors.page import Page as ErrorsPage
from app.fetch.page import FetchPage
from app.forms.page import FormsPage
from app.page import Page as HomePage
from app.patterns.page import Page as PatternsPage
from wybthon import Route, lazy, load_component


def _AboutLazy():
    return ("app.about.page", "Page")


def _TeamLazy():
    return ("app.about.team.page", "Page")


# Example of eager dynamic loader (resolves at route creation time)
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
        Route(path="/fetch", component=FetchPage),
        Route(path="/forms", component=FormsPage),
        Route(path="/errors", component=lambda p: ErrorsPage(p)),
        Route(path="/patterns", component=lambda p: PatternsPage(p)),
        Route(path="/docs/*", component=Docs),
    ]
