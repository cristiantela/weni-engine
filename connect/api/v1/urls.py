from django.urls import path, include
from rest_framework.views import APIView
from rest_framework.response import Response

from .routers import router
from connect import utils
from connect.celery import app as celery_app


class FakeView(APIView):
    authentication_classes = []
    permissions_classes = []

    def get(self, request, format=None):
        org_uuid = request.query_params.get("org")
        channel_type = request.query_params.get("type")

        flow = utils.get_grpc_types().get("flow")

        channels = []

        for channel in flow.list_channel(org_uuid, channel_type):
            channels.append(dict(
                uuid=channel.uuid,
                name=channel.name,
                address=channel.address,
            ))
        
        return Response(channels)


class FakeView2(APIView):
    authentication_classes = []
    permissions_classes = []

    def get(self, request, format=None):
        org_uuid = request.query_params.get("org")
        channel_type = request.query_params.get("type")

        flow = utils.get_grpc_types().get("flow")

        channels = []

        task = celery_app.send_task(  # pragma: no cover
            name="list_channels",
            args=[org_uuid, channel_type],
        )

        task.wait()  # pragma: no cover
        return Response(task.result)


urlpatterns = [
    path("fake", FakeView.as_view()),
    path("fake2", FakeView2.as_view()),
    path("", include(router.urls)),
]
