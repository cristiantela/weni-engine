import json
import uuid
import pendulum
from django.test import RequestFactory
from django.test import TestCase

from connect.api.v1.project.views import ProjectViewSet
from ..organization.serializers import User

from connect.api.v1.organization.views import OrganizationViewSet
from connect.api.v1.tests.utils import create_user_and_token
from connect.common.models import (
    Organization,
    OrganizationAuthorization,
    OrganizationRole,
    Project,
    ProjectAuthorization,
    RequestPermissionOrganization,
    BillingPlan
)

from freezegun import freeze_time
from connect.billing.tasks import end_trial_plan


class CreateOrganizationAPITestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.owner, self.owner_token = create_user_and_token("owner")

    def request(self, data, token=None):
        authorization_header = (
            {"HTTP_AUTHORIZATION": "Token {}".format(token.key)} if token else {}
        )

        request = self.factory.post(
            "/v1/organization/org/",
            json.dumps(data),
            content_type="application/json",
            format="json",
            **authorization_header,
        )

        response = OrganizationViewSet.as_view({"post": "create"})(request, data)
        response.render()
        content_data = json.loads(response.content)
        return (response, content_data)

    def test_create(self):
        User.objects.create(
            email="e@mail.com",
        )
        data = {
            "organization": {
                "name": "name",
                "description": "desc",
                "plan": "plan",
                "authorizations": [
                    {
                        "user_email": "e@mail.com",
                        "role": 3
                    }
                ]
            },
            "project": {
                "date_format": "D",
                "name": "Test Project",
                "organization": "2575d1f9-f7f8-4a5d-ac99-91972e309511",
                "timezone": "America/Argentina/Buenos_Aires",
            }
        }

        response, content_data = self.request(data, self.owner_token)
        self.assertEquals(response.status_code, 201)

    def test_create_template_project(self):
        data = {
            "organization": {
                "name": "name",
                "description": "desc",
                "plan": "plan",
                "authorizations": [
                    {
                        "user_email": "e@mail.com",
                        "role": 3
                    }
                ]
            },
            "project": {
                "date_format": "D",
                "name": "Test Project",
                "organization": "2575d1f9-f7f8-4a5d-ac99-91972e309511",
                "timezone": "America/Argentina/Buenos_Aires",
                "template": True
            }
        }
        response, content_data = self.request(data, self.owner_token)

        self.assertEquals(response.status_code, 201)
        self.assertEquals(content_data.get("project").get("first_access"), True)
        self.assertEquals(content_data.get("project").get("wa_demo_token"), "wa-demo-12345")
        self.assertEquals(content_data.get("project").get("project_type"), "template")
        self.assertEquals(content_data.get("project").get("redirect_url"), "https://wa.me/5582123456?text=wa-demo-12345")
        self.assertEquals(OrganizationAuthorization.objects.count(), 1)
        self.assertEquals(RequestPermissionOrganization.objects.count(), 1)
        self.assertEquals(Project.objects.count(), 1)
        self.assertEquals(ProjectAuthorization.objects.count(), 1)

    def test_create_trial_organization(self):
        User.objects.create(
            email="e@mail.com",
        )
        data = {
            "organization": {
                "name": "name",
                "description": "trial",
                "plan": "trial",
                "authorizations": [
                    {
                        "user_email": "e@mail.com",
                        "role": 3
                    }
                ]
            },
            "project": {
                "date_format": "D",
                "name": "Test Project",
                "organization": "2575d1f9-f7f8-4a5d-ac99-91972e309511",
                "timezone": "America/Argentina/Buenos_Aires",
            }
        }
        response, content_data = self.request(data, self.owner_token)
        self.assertEquals(response.status_code, 201)


class RetrieveOrganizationProjectsAPITestCase(TestCase):

    def setUp(self) -> None:
        self.owner, self.owner_token = create_user_and_token("owner")
        self.factory = RequestFactory()
        self.organization = Organization.objects.create(
            name="will fail",
            description="test organization",
            inteligence_organization=1,
            organization_billing__cycle=BillingPlan.BILLING_CYCLE_MONTHLY,
            organization_billing__plan="free",
        )

        self.organization_authorization = self.organization.authorizations.create(
            user=self.owner, role=OrganizationRole.ADMIN.value
        )

        self.project = self.organization.project.create(
            name="will fail",
            flow_organization=uuid.uuid4(),
            is_template=True
        )

    def request(self, organization_uuid, token=None):
        authorization_header = (
            {"HTTP_AUTHORIZATION": "Token {}".format(token.key)} if token else {}
        )

        request = self.factory.get(
            f"/v1/organization/project/?organization={organization_uuid}&offset=0&limit=12&ordering=",
            content_type="application/json",
            format="json",
            **authorization_header,
        )

        response = OrganizationViewSet.as_view({"get": "list"})(request)
        response.render()
        content_data = json.loads(response.content)
        return (response, content_data)

    def request2(self, project_uuid, token=None):
        authorization_header = (
            {"HTTP_AUTHORIZATION": "Token {}".format(token.key)} if token else {}
        )
        request = self.factory.get(
            f"/v1/organization/project/{project_uuid}/",
            content_type="application/json",
            format="json",
            **authorization_header,
        )
        response = ProjectViewSet.as_view({"get": "list"})(request)
        response.render()
        content_data = json.loads(response.content)
        return response, content_data

    def test_is_template_project(self):
        response, content_data = self.request2(self.project.uuid, self.owner_token)


class PlanAPITestCase(TestCase):

    def setUp(self) -> None:
        self.owner, self.owner_token = create_user_and_token("owner")
        self.factory = RequestFactory()
        self.organization = Organization.objects.create(
            name="will fail",
            description="test organization",
            inteligence_organization=1,
            organization_billing__cycle=BillingPlan.BILLING_CYCLE_MONTHLY,
            organization_billing__plan="free",
        )

        self.trial = Organization.objects.create(
            name="Trial org",
            description="Trial org",
            inteligence_organization=1,
            organization_billing__cycle=BillingPlan.BILLING_CYCLE_MONTHLY,
            organization_billing__plan="trial",
        )

        self.trial_authorization = self.trial.authorizations.create(
            user=self.owner, role=OrganizationRole.ADMIN.value
        )

        self.trial_project = self.trial.project.create(
            name="trial",
            flow_organization=uuid.uuid4(),
            is_template=True,
        )

    def list(self, organization_uuid, token=None):
        authorization_header = (
            {"HTTP_AUTHORIZATION": "Token {}".format(token.key)} if token else {}
        )
        request = self.factory.get(
            f"/v1/organization/org/{organization_uuid}",
            content_type="application/json",
            format="json",
            **authorization_header,
        )
        response = OrganizationViewSet.as_view({"get": "list"})(request)
        response.render()
        content_data = json.loads(response.content)
        return response, content_data

    def test_assert_plans(self):
        response, content_data = self.list(self.organization.uuid, self.owner_token)
        organization = content_data["results"][0]
        self.assertEquals(content_data["count"], 1)
        self.assertEquals(organization["organization_billing"]["plan"], BillingPlan.PLAN_TRIAL)
        self.assertEquals(pendulum.parse(organization["organization_billing"]["trial_end_date"]), pendulum.now().end_of("day").add(months=1))

    def test_end_trial_period(self):
        self.organization.organization_billing.end_trial_period()
        self.assertTrue(self.organization.is_suspended)
        self.assertFalse(self.organization.organization_billing.is_active)

    def test_task_end_trial_plan(self):
        self.trial2 = Organization.objects.create(
            name="Trial 2",
            description="Trial 2",
            inteligence_organization=1,
            organization_billing__cycle=BillingPlan.BILLING_CYCLE_MONTHLY,
            organization_billing__plan="trial",
        )

        date = pendulum.now().add(months=1, days=1)

        with freeze_time(str(date)):
            end_trial_plan()

        org = Organization.objects.get(uuid=self.trial2.uuid)

        self.assertTrue(org.is_suspended)
        self.assertFalse(org.organization_billing.is_active)
