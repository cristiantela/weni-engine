from unittest import skipIf

from django.test import TestCase
from connect.billing import get_gateway
import stripe
from django.conf import settings


@skipIf(not settings.BILLING_SETTINGS.get("stripe", None), "gateway not configured")
class StripeGatewayTestCase(TestCase):
    def setUp(self):
        self.merchant = get_gateway("stripe")
        stripe.api_key = self.merchant.stripe.api_key
        self.stripe = stripe
        self.customer = "cus_KzFc41F3yLCLoO"

    def testPurchase(self):
        resp = self.merchant.purchase(10, self.customer)
        self.assertEquals(resp["status"], "SUCCESS")

    def testPurchaseDecimalAmount(self):
        resp = self.merchant.purchase(10.99, self.customer)
        self.assertEquals(resp["status"], "SUCCESS")

    def test_last_2(self):
        resp = self.merchant.get_card_data(self.customer)
        self.assertEquals(resp['response'][0]['last2'], '42')

    def test_brand(self):
        resp = self.merchant.get_card_data(self.customer)
        self.assertEquals(resp['response'][0]['brand'], 'visa')

    def test_get_card_data(self):
        resp = self.merchant.get_card_data(self.customer)
        self.assertEquals(resp['status'], 'SUCCESS')

    def test_get_user_detail_data(self):
        resp = self.merchant.get_user_detail_data(self.customer)
        self.assertEquals(resp['status'], 'SUCCESS')

    def test_get_payment_method_details(self):
        resp = self.merchant.get_payment_method_details("ch_3K9wZYGB60zUb40p1C0iiskn")
        self.assertEquals(resp['status'], 'SUCCESS')
        self.assertEquals(resp['response']['final_card_number'], '4242')
        self.assertEquals(resp['response']['brand'], 'visa')

    def test_get_payment_method_details_fail(self):
        resp = self.merchant.get_payment_method_details("ch_3K9wZYGB60zUb40p1C0iisk")
        self.assertEquals(resp['status'], 'FAIL')


class OdooGatewayTestCase(TestCase):
    def setUp(self):
        self.odoo = get_gateway("odoo")

    def test_connection_information(self):
        common = self.odoo.common
        self.assertEquals(type(common.version()), dict)
        self.assertEquals(common.version()['server_version'], '12.0')

    def test_odoo_authentication(self):
        uid = self.odoo.authenticate()
        self.assertEquals(type(uid), int)

    def test_list_invoices(self):
        invoices = self.odoo.list_invoices()
        self.assertEquals(invoices["status"], "SUCCESS")

    def test_get_invoice(self):
        invoice = self.odoo.get_invoice([63])
        self.assertEquals(invoice["status"], "SUCCESS")
