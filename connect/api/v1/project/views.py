import json
from django.shortcuts import get_object_or_404
from django.utils.translation import ugettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone
import pendulum
from connect.billing.models import Contact
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.exceptions import ValidationError

from connect.api.v1.metadata import Metadata
from connect.api.v1.project.filters import ProjectOrgFilter
from connect.api.v1.project.permissions import ProjectHasPermission
from connect.api.v1.internal.permissions import ModuleHasPermission
from connect.api.v1.organization.permissions import Has2FA
from connect.api.v1.project.serializers import (
    ProjectSerializer,
    ProjectSearchSerializer,
    RequestRocketPermissionSerializer,
    RequestPermissionProjectSerializer,
    ReleaseChannelSerializer,
    ListChannelSerializer,
    CreateChannelSerializer,
    CreateWACChannelSerializer,
    DestroyClassifierSerializer,
    RetrieveClassifierSerializer,
    CreateClassifierSerializer,
    ClassifierSerializer,
    TemplateProjectSerializer,
)

from connect.celery import app as celery_app
from connect.common.models import (
    Organization,
    OrganizationAuthorization,
    Project,
    RequestPermissionProject,
    RequestRocketPermission,
    ProjectAuthorization,
    RocketAuthorization,
    OpenedProject,
    TemplateProject,
)
from connect.authentication.models import User
from connect.common import tasks
from connect.utils import count_contacts

from connect.api.grpc.project.serializers import CreateClassifierRequestSerializer
from connect.api.v1.internal.flows.flows_rest_client import FlowsRESTClient
from connect.api.v1.internal.intelligence.intelligence_rest_client import IntelligenceRESTClient
from weni.protobuf.flows.classifier_pb2 import ClassifierCreateRequest


class ProjectViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, ProjectHasPermission, Has2FA]
    filter_class = ProjectOrgFilter
    filter_backends = [OrderingFilter, SearchFilter, DjangoFilterBackend]
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

        filter = Q(
            project_authorizations__user=self.request.user
        ) & ~Q(
            project_authorizations__role=0
        ) & Q(
            opened_project__user=self.request.user
        )
        return self.queryset.filter(organization__pk__in=auth).filter(filter).order_by("-opened_project__day")

    def perform_destroy(self, instance):
        flow_organization = instance.flow_organization
        instance.delete()

        celery_app.send_task(
            "delete_project",
            args=[flow_organization, self.request.user.email],
        )

    def perform_project_authorization_destroy(self, instance, is_request_permission):
        flow_organization = instance.project.flow_organization
        if not is_request_permission:
            celery_app.send_task(
                "delete_user_permission_project",
                args=[flow_organization, instance.user.email, instance.role],
            )
        instance.delete()

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

    @action(
        detail=True,
        methods=["GET"],
        url_name="get-contact-active-detailed",
        url_path="grpc/get-contact-active-detailed/(?P<project_uuid>[^/.]+)",
    )
    def get_contact_active_detailed(self, request, project_uuid):

        before = request.query_params.get("before")
        after = request.query_params.get("after")

        if not before or not after:
            raise ValidationError(
                _("Need to pass 'before' and 'after' in query params")
            )

        before = pendulum.parse(before, strict=False).end_of("day")
        after = pendulum.parse(after, strict=False).start_of("day")

        contact_count = count_contacts(str(project_uuid), before, after)
        contacts = Contact.objects.filter(channel__project=project_uuid, last_seen_on__range=(after, before))

        project = Project.objects.get(uuid=project_uuid)

        active_contacts_info = []
        for contact in contacts:
            active_contacts_info.append({"name": contact.name, "uuid": contact.contact_flow_uuid})

        project_info = {
            "project_name": project.name,
            "active_contacts": contact_count,
            "contacts_info": active_contacts_info,
        }

        contact_detailed = {"projects": project_info}
        return JsonResponse(data=contact_detailed, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["DELETE"],
        url_name="destroy-user-permission",
        url_path="grpc/destroy-user-permission/(?P<project_uuid>[^/.]+)",
    )
    def destroy_user_permission(self, request, project_uuid):
        user_email = request.data.get('email')
        project = get_object_or_404(Project, uuid=project_uuid)

        project_permission = project.project_authorizations.filter(
            user__email=user_email
        )
        request_permission = project.requestpermissionproject_set.filter(
            email=user_email
        )

        organization_auth = project.organization.authorizations.filter(
            user__email=user_email
        )

        if request_permission.exists():
            self.perform_project_authorization_destroy(request_permission.first(), True)
            return Response(status=status.HTTP_204_NO_CONTENT)

        elif project_permission.exists() and organization_auth.exists():
            organization_auth = organization_auth.first()
            if not organization_auth.is_admin:
                self.perform_project_authorization_destroy(project_permission.first(), False)
                return Response(status=status.HTTP_204_NO_CONTENT)
            else:
                return Response(status=status.HTTP_401_UNAUTHORIZATED)
        return Response(status=status.HTTP_404_NOT_FOUND)

    @action(
        detail=True,
        methods=["POST"],
        url_name="update-last-opened-on",
        url_path="update-last-opened-on/(?P<project_uuid>[^/.]+)",
    )
    def update_last_opened_on(self, request, project_uuid):
        user_email = request._user
        project = get_object_or_404(Project, uuid=project_uuid)
        user = User.objects.get(email=user_email)
        last_opened_on = OpenedProject.objects.filter(user=user, project=project)
        if(last_opened_on.exists()):
            last_opened_on = last_opened_on.first()
            last_opened_on.day = timezone.now()
            last_opened_on.save()
        else:
            OpenedProject.objects.create(project=project, user=user, day=timezone.now())
        return JsonResponse(status=status.HTTP_200_OK, data={"day": str(last_opened_on.day)})

    @action(
        detail=True,
        methods=["GET"],
        url_name="list-channel",
        permission_classes=[ModuleHasPermission],
    )
    def list_channel(self, request):
        channel_type = request.data.get('channel_type', None)
        if not channel_type:
            raise ValidationError("Need pass the channel_type")

        page = self.paginate_queryset(
            self.filter_queryset(self.queryset),
        )
        context = self.get_serializer_context()
        context["channel_type"] = channel_type
        channel_serializer = ListChannelSerializer(page, many=True, context=context)
        return self.get_paginated_response(channel_serializer.data)

    @action(
        detail=True,
        methods=["GET"],
        url_name="realease-channel",
        serializer_class=ReleaseChannelSerializer,
        permission_classes=[ModuleHasPermission],
    )
    def release_channel(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = tasks.realease_channel.delay(
            channel_uuid=serializer.validated_data.get("channel_uuid"),
            user=serializer.validated_data.get("user"),
        )
        task.wait()
        return JsonResponse(status=status.HTTP_200_OK, data={"release": task.result})

    @action(
        detail=True,
        methods=["POST"],
        url_name='create-channel',
        serializer_class=CreateChannelSerializer,
        permission_classes=[ModuleHasPermission],
    )
    def create_channel(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            project_uuid = serializer.validated_data.get("project_uuid")
            project = Project.objects.get(uuid=project_uuid)
            task = tasks.create_channel.delay(
                user=serializer.validated_data.get("user"),
                project_uuid=str(project.flow_organization),
                data=json.dumps(serializer.validated_data.get("data")),
                channeltype_code=serializer.validated_data.get("channeltype_code"),
            )
            task.wait()
            return JsonResponse(status=status.HTTP_200_OK, data=task.result)

    @action(
        detail=True,
        methods=["POST"],
        url_name='create-wac-channel',
        serializer_class=CreateWACChannelSerializer,
        permission_classes=[ModuleHasPermission],
    )
    def create_wac_channel(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            project_uuid = serializer.validated_data.get("project_uuid")
            project = Project.objects.get(uuid=project_uuid)
            task = tasks.create_wac_channel.delay(
                user=serializer.validated_data.get("user"),
                flow_organization=str(project.flow_organization),
                config=serializer.validated_data.get("config"),
                phone_number_id=serializer.validated_data.get("phone_number_id"),
            )

            task.wait()
            return JsonResponse(status=status.HTTP_200_OK, data=task.result)

    @action(
        detail=True,
        methods=["DELETE"],
        url_name='destroy-classifier',
        serializer_class=DestroyClassifierSerializer,
        permission_classes=[ModuleHasPermission],
    )
    def destroy_classifier(self, request):
        serializer = DestroyClassifierSerializer(data=request.query_params)
        if serializer.is_valid(raise_exception=True):
            classifier_uuid = serializer.validated_data.get("uuid")
            user_email = serializer.validated_data.get("user_email")

            task = tasks.destroy_classifier.delay(str(classifier_uuid), user_email)
            task.wait()
            return JsonResponse(status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["GET"],
        url_name='retrieve-classifier',
        serializer_class=RetrieveClassifierSerializer,
        permission_classes=[ModuleHasPermission],
    )
    def retrieve_classifier(self, request):
        serializer = RetrieveClassifierSerializer(data=request.query_params)

        if serializer.is_valid(raise_exception=True):
            classifier_uuid = serializer.validated_data.get("uuid")

            task = tasks.retrieve_classifier.delay(str(classifier_uuid))
            task.wait()
            return JsonResponse(status=status.HTTP_200_OK, data=task.result)

    @action(
        detail=True,
        methods=["POST"],
        url_name='create-classifier',
        serializer_class=CreateClassifierSerializer,
        permission_classes=[ModuleHasPermission],
    )
    def create_classifier(self, request):
        request_data = request.query_params
        serializer = CreateClassifierSerializer(data=request_data)
        if serializer.is_valid(raise_exception=True):
            project_uuid = serializer.validated_data.get("project_uuid")
            project = Project.objects.get(uuid=project_uuid)
            task = tasks.create_classifier.delay(
                project_uuid=str(project.flow_organization),
                user_email=serializer.validated_data.get("user"),
                classifier_name=serializer.validated_data.get("name"),
                access_token=serializer.validated_data.get("access_token"),
            )
            task.wait()
            return JsonResponse(status=status.HTTP_200_OK, data=task.result)

    @action(
        detail=True,
        methods=["GET"],
        url_name='list-classifier',
        serializer_class=ClassifierSerializer,
        permission_classes=[ModuleHasPermission],
    )
    def list_classifier(self, request):
        serializer = ClassifierSerializer(data=request.query_params)
        if serializer.is_valid(raise_exception=True):
            project_uuid = serializer.validated_data.get("project_uuid")
            project = Project.objects.get(uuid=project_uuid)
            task = tasks.list_classifier.delay(str(project.flow_organization))
            task.wait()
            return JsonResponse(status=status.HTTP_200_OK, data=task.result)


class RequestPermissionProjectViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    queryset = RequestPermissionProject.objects.all()
    serializer_class = RequestPermissionProjectSerializer
    permission_classes = [IsAuthenticated]
    metadata_class = Metadata

    def create(request, *args, **kwargs):
        created_by = request.request.user
        role = request.request.data.get('role')
        email = request.request.data.get('email')
        project_uuid = request.request.data.get('project')
        rocket_role = request.request.data.get('rocket_authorization')
        project = Project.objects.filter(uuid=project_uuid)

        if len(email) == 0:
            return Response({"status": 400, "message": "E-mail field isn't valid!"})

        if len([item for item in ProjectAuthorization.ROLE_CHOICES if item[0] == role]) == 0:
            return Response({"status": 422, "message": f"{role} is not a valid role!"})
        if len(project) == 0:
            return Response({"status": 404, "message": f"Project {project_uuid} not found!"})
        project = project.first()

        if len([item for item in RocketAuthorization.ROLE_CHOICES if item[0] == rocket_role]) == 0 and rocket_role:
            return Response({"status": 422, "message": f"{rocket_role} is not a valid rocket role!"})

        request_permission = RequestPermissionProject.objects.filter(email=email, project=project)
        project_auth = project.project_authorizations.filter(user__email=email)

        request_rocket_authorization = RequestRocketPermission.objects.filter(email=email, project=project)
        rocket_authorization = None

        user_name = ''
        first_name = ''
        last_name = ''
        photo = ''
        is_pendent = False

        if request_permission.exists():
            request_permission = request_permission.first()
            is_pendent = True
            request_permission.role = role
            request_permission.save()
        elif project_auth.exists():
            project_auth = project_auth.first()
            rocket_authorization = project_auth.rocket_authorization
            user_name = project_auth.user.username
            first_name = project_auth.user.first_name
            last_name = project_auth.user.last_name
            photo = project_auth.user.photo_url
            project_auth.role = role
            project_auth.save()
        else:
            RequestPermissionProject.objects.create(created_by=created_by, email=email, role=role, project=project)
            is_pendent = RequestPermissionProject.objects.filter(email=email, project=project).exists()

        if request_rocket_authorization.exists():
            request_rocket_authorization = request_rocket_authorization.first()
            request_rocket_authorization.role = rocket_role
            request_rocket_authorization.save()
        elif not (rocket_authorization is None):
            rocket_authorization.role = rocket_role
            rocket_authorization.save()
        elif rocket_role:
            RequestRocketPermission.objects.create(email=email, role=rocket_role, project=project, created_by=created_by)

        return Response({"status": 200, "data": {"created_by": created_by.email, "role": role, "rocket_authorization": rocket_role, "email": email, "project": project_uuid, "username": user_name, "first_name": first_name, "last_name": last_name, "photo_user": photo, "is_pendent": is_pendent}})


class RequestPermissionRocketViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    queryset = RequestRocketPermission.objects.all()
    serializer_class = RequestRocketPermissionSerializer
    permission_classes = [IsAuthenticated]
    metadata_class = Metadata
    lookup_field = "pk"


class TemplateProjectViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    queryset = TemplateProject.objects
    serializer_class = TemplateProjectSerializer
    permission_classes = [IsAuthenticated]
    metadata_class = Metadata
    lookup_field = "pk"

    def get_queryset(self, *args, **kwargs):
        if getattr(self, "swagger_fake_view", False):
            # queryset just for schema generation metadata
            return TemplateProject.objects.none()  # pragma: no cover
        auth = (
            ProjectAuthorization.objects.exclude(role=0)
            .filter(user=self.request.user)
        )
        return self.queryset.filter(authorization__in=auth)

    def get_object(self):
        lookup_url_kwarg = self.lookup_field

        obj = self.get_queryset().get(authorization__project__uuid=self.kwargs.get(lookup_url_kwarg))

        return obj

    def create(self, request, *args, **kwargs):

        flow_organization = tasks.create_template_project(
            request.data.get("name"), request.user.email, request.data.get("timezone")
        ).get("uuid")
        organization = get_object_or_404(Organization, uuid=request.data.get("organization"))

        # Create blank project

        project = Project.objects.create(
            date_format=request.data.get("date_format"),
            name=request.data.get("name"),
            organization=organization,
            timezone=request.data.get("timezone"),
            flow_organization=flow_organization
        )

        authorization = project.get_user_authorization(request.user)

        # Create template model

        template = self.queryset.create(
            authorization=authorization,
            project=project
        )

        # Get AI access token
        inteligence_client = IntelligenceRESTClient()
        access_token = inteligence_client.get_access_token(request.user.email)

        # Create classifier
        classifier_request = ClassifierCreateRequest(
            org=str(template.project.flow_organization),
            user=request.user.email,
            classifier_type="bothub",
            name="template classifier",
            access_token=access_token
        )

        classifier_serializer = CreateClassifierRequestSerializer(message=classifier_request)

        classifier_uuid = tasks.create_classifier(
            project_uuid=str(project.flow_organization),
            user_email=classifier_serializer.validated_data.get("user"),
            classifier_type="bothub",
            classifier_name=classifier_serializer.validated_data.get("name"),
            access_token=classifier_serializer.validated_data.get("access_token"),
        ).get("uuid")

        # Create Flow
        rest_client = FlowsRESTClient()

        flows = rest_client.create_flows(str(project.flow_organization), classifier_uuid)

        flow_uuid = flows.get("uuid")

        template.classifier_uuid = classifier_uuid
        template.flow_uuid = flow_uuid

        # Integrate WhatsApp
        token = self.request._auth
        wa_demo_token = tasks.whatsapp_demo_integration(str(template.project.flow_organization), token=token)

        template.wa_demo_token = wa_demo_token
        template.save(update_fields=["classifier_uuid", "flow_uuid", "wa_demo_token"])

        data = {
            "first_acess": template.first_access,
            "flow_uuid": template.flow_uuid,
            "project_type": "template",
            "wa_demo_token": template.wa_demo_token
        }

        return Response(data, status=status.HTTP_201_CREATED)
