"""Route table for the E2E fixture.

One top-level route per feature (matching :data:`app.featuremeta.FEATURES`)
plus a handful of nested ``/router/...`` routes used to exercise route
params, query strings, wildcards, nested children, and the not-found path.
"""

from app.features import components as components_feat
from app.features import context as context_feat
from app.features import errors as errors_feat
from app.features import events as events_feat
from app.features import flow as flow_feat
from app.features import forms as forms_feat
from app.features import holes as holes_feat
from app.features import portal as portal_feat
from app.features import props as props_feat
from app.features import reactivity as reactivity_feat
from app.features import router as router_feat
from app.features import stores as stores_feat
from app.features import suspense as suspense_feat
from app.testkit import tid

from wybthon import Route, component, div, lazy, load_component

LazyPanel = lazy(lambda: ("app.features.lazy_target", "LoadedPanel"))
LazyMissing = load_component("app.features.does_not_exist", "Missing")


@component
def Home():
    return div("home", **tid("page-home"))


@component
def Blank():
    return div("blank", **tid("page-blank"))


@component
def NotFound(query=None, params=None):
    return div("not found", **tid("page-not-found"))


def create_routes():
    return [
        Route(path="/", component=Home),
        Route(path="/blank", component=Blank),
        Route(path="/reactivity", component=reactivity_feat.Page),
        Route(path="/holes", component=holes_feat.Page),
        Route(path="/props", component=props_feat.Page),
        Route(path="/events", component=events_feat.Page),
        Route(path="/context", component=context_feat.Page),
        Route(path="/flow", component=flow_feat.Page),
        Route(path="/forms", component=forms_feat.Page),
        Route(path="/stores", component=stores_feat.Page),
        Route(path="/suspense", component=suspense_feat.Page),
        Route(path="/errors", component=errors_feat.Page),
        Route(path="/components", component=components_feat.Page),
        Route(path="/lazy", component=LazyPanel),
        Route(path="/lazy-error", component=LazyMissing),
        Route(path="/portal", component=portal_feat.Page),
        Route(path="/router", component=router_feat.Index),
        Route(path="/router/user/:id", component=router_feat.User),
        Route(path="/router/search", component=router_feat.Search),
        Route(path="/router/docs/*", component=router_feat.Docs),
        Route(
            path="/router/parent",
            component=router_feat.Parent,
            children=[Route(path="child", component=router_feat.Child)],
        ),
    ]
