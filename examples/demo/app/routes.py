from app.about.page import Page as AboutPage
from app.errors.page import Page as ErrorsPage
from app.fetch.page import FetchPage
from app.forms.page import FormsPage
from app.page import Page as HomePage
from wybthon import Route


def create_routes():
    return [
        Route(path="/", component=lambda p: HomePage(p)),
        Route(path="/about", component=lambda p: AboutPage(p)),
        Route(path="/fetch", component=FetchPage),
        Route(path="/forms", component=FormsPage),
        Route(path="/errors", component=lambda p: ErrorsPage(p)),
    ]
