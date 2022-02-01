import xmlrpc.client
from connect.billing import GatewayNotConfigured
from django.conf import settings


class OdooGateway:
    display_name = "Odoo"

    def __init__(self):
        odoo_settings = [
            settings.ODOO_BASE_URL,
            settings.ODOO_DB,
            settings.ODOO_USERNAME,
            settings.ODOO_PASSWORD,
        ]
        if None in odoo_settings:
            raise GatewayNotConfigured(
                "The '{self.display_name}' gateway is not correctly " "configured."
            )

        self.url = settings.ODOO_BASE_URL
        self.db = settings.ODOO_DB
        self.username = settings.ODOO_USERNAME
        self.password = settings.ODOO_PASSWORD
        self.common = self.__meta_calls()
        self.authenticate()

    def __meta_calls(self):
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        return common

    def authenticate(self):
        uid = self.common.authenticate(self.db, self.username, self.password, {})
        self.uid = uid
        return uid

    @property
    def models(self):
        models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        return models

    def check_access_right(self, model: str, method: str):
        """Verifies whether the current user has access to the model itself"""
        return self.models.execute_kw(
            self.db,
            self.uid,
            self.password,
            model,
            "check_access_rights",
            [method],
            {"raise_exception": False},
        )

    def list_invoices(self, args=[]):
        if not self.check_access_right("account.invoice", "read"):
            return {"status": "FAIL", "message": "User don't have Read permissions"}

        invoices = self.models.execute_kw(
            self.db, self.uid, self.password, "account.invoice", "search", [args]
        )

        return {"status": "SUCCESS", "invoices": invoices}

    def get_invoice(self, id: list):
        if not self.check_access_right("account.invoice", "read"):
            return {"status": "FAIL", "message": "User don't have Read permissions"}

        invoice = self.models.execute_kw(
            self.db, self.uid, self.password, "account.invoice", "read", id
        )
        return {"status": "SUCCESS", "invoice": invoice}
