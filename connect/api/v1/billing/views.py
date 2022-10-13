import logging
from django.conf import settings
from rest_framework import viewsets
from rest_framework.decorators import action
import stripe
from stripe.api_resources.customer import Customer
from django.http import JsonResponse
from rest_framework import status
from connect.common.models import BillingPlan
from connect import billing


logger = logging.getLogger(__name__)


class BillingViewSet(viewsets.ViewSet):
    """
    A simple ViewSet for billing actions.
    """

    @action(
        detail=True,
        methods=["POST"],
        url_name="setup-intent",
        url_path="setup_plan/",
    )
    def setup_intent(self, request):
        stripe.api_key = settings.BILLING_SETTINGS.get("stripe", {}).get("API_KEY")
        if settings.TESTING:
            customer = Customer(id="cus_MYOrndkgpPHGK9")
            setup_intent = stripe.SetupIntent(
                customer=customer.id,
                id="seti_test_string"
            )

        else:
            customer = stripe.Customer.create()
            setup_intent = stripe.SetupIntent.create(
                customer=customer.id
            )

        data = {
            "setup_intent": setup_intent,
            "customer": customer.id,
        }
        return JsonResponse(data=data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["POST"],
        url_name="setup-plan",
        url_path="setup_plan/",
    )
    def setup_plan(self, request):
        stripe.api_key = settings.BILLING_SETTINGS.get("stripe", {}).get("API_KEY")

        plan = request.data.get("plan")
        customer = request.data.get("customer")

        if plan == BillingPlan.PLAN_BASIC:
            price = BillingPlan().plan_basic_info["price"]

        elif plan == BillingPlan.PLAN_PLUS:
            price = BillingPlan().plan_plus_info["price"]

        elif plan == BillingPlan.PLAN_PREMIUM:
            price = BillingPlan().plan_premium_info["price"]

        elif plan == BillingPlan.PLAN_ENTERPRISE:
            price = BillingPlan().plan_enterprise_info["price"]
        else:
            price = 0

        data = {
            "customer": customer,
            "plan": plan,
            "price": price ,
        }

        if settings.TESTING:
            p_intent = stripe.PaymentIntent(amount_received=price, id="pi_test_id", amount=price, charges={"amount": price, "amount_captured": price})
            purchase_result = {"status": "SUCCESS", "response": p_intent}
            data["status"] = "SUCCESS"
        else:
            try:
                gateway = billing.get_gateway("stripe")
                purchase_result = gateway.purchase(
                    money=int(price),
                    identification=customer,
                )
                data["status"] = purchase_result["status"]
            except Exception as error:
                logger.error(f"Stripe error: {error}")
                data["status"] = "FAILURE"

        return JsonResponse(data=data, status=status.HTTP_200_OK)
