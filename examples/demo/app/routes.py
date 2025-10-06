from app.about.page import Page as AboutPage
from app.about.team.page import Page as TeamPage
from app.docs.page import Page as DocsPage
from app.errors.page import Page as ErrorsPage
from app.fetch.page import FetchPage
from app.forms.page import FormsPage
from app.page import Page as HomePage
from wybthon import Route


def create_routes():
    return [
        Route(path="/", component=lambda p: HomePage(p)),
        Route(
            path="/about",
            component=lambda p: AboutPage(p),
            children=[
                Route(path="team", component=lambda p: TeamPage(p)),
            ],
        ),
        Route(path="/fetch", component=FetchPage),
        Route(path="/forms", component=FormsPage),
        Route(path="/errors", component=lambda p: ErrorsPage(p)),
        Route(path="/docs/*", component=lambda p: DocsPage(p)),
    ]
