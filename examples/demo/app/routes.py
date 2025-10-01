from wybthon import Route
from app.page import Page as HomePage
from app.about.page import Page as AboutPage
from app.fetch.page import FetchPage
from app.forms.page import FormsPage
from app.errors.page import Page as ErrorsPage


def create_routes():
    return [
        Route(path="/", component=lambda p: HomePage(p)),
        Route(path="/about", component=lambda p: AboutPage(p)),
        Route(path="/fetch", component=FetchPage),
        Route(path="/forms", component=FormsPage),
        Route(path="/errors", component=lambda p: ErrorsPage(p)),
    ]
