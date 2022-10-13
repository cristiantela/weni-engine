import json
import uuid
import pendulum
import stripe
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
from rest_framework import status
from freezegun import freeze_time
from connect.billing.tasks import end_trial_plan
from connect.api.v1.billing.views import BillingViewSet
from django.conf import settings


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

        self.trial.organization_billing.stripe_customer = "cus_MYOrndkgpPHGK9"
        self.trial.organization_billing.save(update_fields=["stripe_customer"])

        self.trial_authorization = self.trial.authorizations.create(
            user=self.owner, role=OrganizationRole.ADMIN.value
        )

        self.trial_project = self.trial.project.create(
            name="trial",
            flow_organization=uuid.uuid4(),
            is_template=True,
        )

        self.basic = Organization.objects.create(
            name="basic org",
            description="basic org",
            inteligence_organization=1,
            organization_billing__cycle=BillingPlan.BILLING_CYCLE_MONTHLY,
            organization_billing__plan="basic",
        )

        self.basic_authorization = self.basic.authorizations.create(
            user=self.owner, role=OrganizationRole.ADMIN.value
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

    def request_upgrade_plan(self, organization_uuid=None, data=None, token=None):

        authorization_header = (
            {"HTTP_AUTHORIZATION": "Token {}".format(token.key)} if token else {}
        )
        request = self.factory.patch(
            f"/v1/organization/org/billing/upgrade-plan/{organization_uuid}",
            content_type="application/json",
            data=json.dumps(data),
            format="json",
            **authorization_header,
        )
        response = OrganizationViewSet.as_view({"patch": "upgrade_plan"})(request, organization_uuid)
        content_data = json.loads(response.content)
        return response, content_data

    def test_assert_plans(self):
        response, content_data = self.list(self.organization.uuid, self.owner_token)
        organization = content_data["results"][1]
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

    def test_upgrade_plan(self):
        data = {
            "organization_billing_plan": "basic"
        }
        response, content_data = self.request_upgrade_plan(
            organization_uuid=self.trial.uuid,
            data=data,
            token=self.owner_token
        )

        self.assertEquals(content_data["status"], "SUCCESS")
        self.assertEquals(content_data["old_plan"], BillingPlan.PLAN_TRIAL)
        self.assertEquals(content_data["plan"], BillingPlan.PLAN_BASIC)
        self.assertEquals(response.status_code, status.HTTP_200_OK)

    def test_upgrade_plan_stripe_failure(self):
        data = {
            "organization_billing_plan": "basic",
            "stripe_failure": True
        }
        response, content_data = self.request_upgrade_plan(
            organization_uuid=self.trial.uuid,
            data=data,
            token=self.owner_token
        )
        self.assertEquals(content_data["status"], "FAILURE")
        self.assertEquals(content_data["message"], "Stripe error")
        self.assertEquals(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def test_upgrade_plan_change_failure(self):
        data = {
            "organization_billing_plan": "basic",
            "plan_failure": True
        }
        response, content_data = self.request_upgrade_plan(
            organization_uuid=self.trial.uuid,
            data=data,
            token=self.owner_token
        )
        self.assertEquals(content_data["status"], "FAILURE")
        self.assertEquals(content_data["message"], "Invalid plan choice")
        self.assertEquals(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upgrade_plan_empty_failure(self):
        data = {
            "organization_billing_plan": "plan_2",
        }
        response, content_data = self.request_upgrade_plan(
            organization_uuid=self.basic.uuid,
            data=data,
            token=self.owner_token
        )
        self.assertEquals(content_data["status"], "FAILURE")
        self.assertEquals(content_data["message"], "Empty customer")
        self.assertEquals(response.status_code, status.HTTP_304_NOT_MODIFIED)


class BillingViewTestCase(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.stripe = stripe
        self.stripe.api_key = settings.BILLING_SETTINGS.get("stripe", {}).get("API_KEY")
        self.customer = ""
        self.owner, self.owner_token = create_user_and_token("owner")

    def request(self, data=None, method=None):
        request = self.factory.post(
            f"/v1/billing/{method}",
            data=json.dumps(data),
            content_type="application/json",
            format="json",
        )

        response = BillingViewSet.as_view({"post": method})(request)

        content_data = json.loads(response.content)
        return (response, content_data)

    def request_create_org(self, data, token=None):
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

    def test_setup_intent(self):
        response, content_data = self.request(method="setup_intent")
        # setup card
        stripe.Customer.create_source(
            content_data.get("customer"),
            source="tok_visa",
        )
        self.customer = content_data.get("customer")
        self.assertEquals(content_data.get("customer"), "cus_MYOrndkgpPHGK9")

    def test_setup_plan(self):
        data = {
            "plan": "basic",
            "customer": "cus_MYOrndkgpPHGK9",
        }
        response, content_data = self.request(data=data, method="setup_plan")
        self.assertEquals(content_data["status"], "SUCCESS")
        # create organization after success at stripe
        User.objects.create(
            email="e@mail.com",
        )

        create_org_data = {
            "organization": {
                "name": "basic",
                "description": "basic",
                "plan": "basic",
                "authorizations": [
                    {
                        "user_email": "e@mail.com",
                        "role": 3
                    }
                ]
            },
            "project": {
                "date_format": "D",
                "name": "Test Project basic",
                "organization": "2575d1f9-f7f8-4a5d-ac99-91972e309511",
                "timezone": "America/Argentina/Buenos_Aires",
            }
        }
        response, content_data = self.request_create_org(create_org_data, self.owner_token)
        self.assertEquals(content_data["organization"]["organization_billing"]["plan"], BillingPlan.PLAN_BASIC)


class TaskTestCase(TestCase):
    def setUp(self):
        self.basic = Organization.objects.create(
            name="basic",
            description="test basic",
            inteligence_organization=1,
            organization_billing__cycle=BillingPlan.BILLING_CYCLE_MONTHLY,
            organization_billing__plan=BillingPlan.PLAN_BASIC,
        )
        self.plus = Organization.objects.create(
            name="plus",
            description="test plus",
            inteligence_organization=1,
            organization_billing__cycle=BillingPlan.BILLING_CYCLE_MONTHLY,
            organization_billing__plan=BillingPlan.PLAN_PLUS,
        )
        self.premium = Organization.objects.create(
            name="premium",
            description="test premium",
            inteligence_organization=1,
            organization_billing__cycle=BillingPlan.BILLING_CYCLE_MONTHLY,
            organization_billing__plan=BillingPlan.PLAN_PREMIUM,
        )
        self.enterprise = Organization.objects.create(
            name="enterprise",
            description="test enterprise",
            inteligence_organization=1,
            organization_billing__cycle=BillingPlan.BILLING_CYCLE_MONTHLY,
            organization_billing__plan=BillingPlan.PLAN_ENTERPRISE,
        )
