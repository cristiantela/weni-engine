from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import ugettext_lazy as _
from django_filters import rest_framework as filters
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import PermissionDenied

from connect.common.models import Project, Organization


class ProjectOrgFilter(filters.FilterSet):
    class Meta:
        model = Project
        fields = ["organization"]

    organization = filters.CharFilter(
        field_name="organization",
        method="filter_organization_uuid",
        help_text=_("Organization's UUID"),
    )

    def filter_organization_uuid(self, queryset, name, value):  # pragma: no cover
        request = self.request
        try:
            organization = Organization.objects.get(uuid=value)
            authorization = organization.get_user_authorization(request.user)
            if not authorization.can_read:
                raise PermissionDenied()
            new_queryset = queryset.filter(organization=organization)
            return new_queryset.filter(project_authorizations__user=request.user)
        except Organization.DoesNotExist:
            raise NotFound(_("Organization {} does not exist").format(value))
        except DjangoValidationError:
            raise NotFound(_("Invalid organization UUID"))
