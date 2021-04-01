from django.utils.translation import ugettext_lazy as _
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from weni.api.v1.metadata import Metadata
from weni.api.v1.project.filters import ProjectOrgFilter
from weni.api.v1.project.permissions import ProjectHasPermission
from weni.api.v1.project.serializers import ProjectSeralizer, ProjectSearchSerializer
from weni.celery import app as celery_app
from weni.common.models import OrganizationAuthorization, Project


class ProjectViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    queryset = Project.objects.all()
    serializer_class = ProjectSeralizer
    permission_classes = [IsAuthenticated, ProjectHasPermission]
    filter_class = ProjectOrgFilter
    lookup_field = "uuid"
    metadata_class = Metadata

    def get_queryset(self, *args, **kwargs):
        if getattr(self, "swagger_fake_view", False):
            # queryset just for schema generation metadata
            return Project.objects.none()  # pragma: no cover
        auth = (
            OrganizationAuthorization.objects.exclude(role=0)
            .filter(user=self.request.user)
            .values("organization")
        )
        return self.queryset.filter(organization__pk__in=auth)

    def perform_destroy(self, instance):
        flow_organization = instance.flow_organization
        instance.delete()

        celery_app.send_task(
            "delete_project",
            args=[flow_organization, self.request.user.email],
        )

    @action(
        detail=True,
        methods=["GET"],
        url_name="project-search",
        serializer_class=ProjectSearchSerializer,
    )
    def project_search(self, request, **kwargs):  # pragma: no cover
        serializer = ProjectSearchSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        project = Project.objects.get(pk=serializer.data.get("project_uuid"))

        user_authorization = project.organization.get_user_authorization(
            self.request.user
        )
        if not user_authorization.can_contribute:
            raise PermissionDenied(
                _("You can't contribute in this organization")
            )  # pragma: no cover

        task = celery_app.send_task(  # pragma: no cover
            name="search_project",
            args=[
                project.organization.inteligence_organization,
                str(project.flow_organization),
                serializer.data.get("text"),
            ],
        )
        task.wait()  # pragma: no cover

        return Response(task.result)
