import xmlrpc.client
from connect.billing import GatewayNotConfigured
from django.conf import settings


class OdooGateway:
    display_name = "Odoo"

    def __init__(self):
        odoo_settings = [settings.ODOO_BASE_URL, settings.ODOO_DB, settings.ODOO_USERNAME, settings.ODOO_PASSWORD]
        if None in odoo_settings:
            raise GatewayNotConfigured(
                "The '{self.display_name}' gateway is not correctly " "configured."
            )

        self.url = settings.ODOO_BASE_URL
        self.db = settings.ODOO_DB
        self.username = settings.ODOO_USERNAME
        self.password = settings.ODOO_PASSWORD
        self.common = self.__meta_calls()

    def __meta_calls(self):
        common = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/common')
        return common

    def authenticate(self):
        uid = self.common.authenticate(self.db, self.username, self.password, {})
        self.uid = uid
        return uid

    @property
    def models(self):
        models = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/object')
        return models

    def check_access_right(self):
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            'res.partner', 'check_access_rights',
            ['read'], {'raise_exception': False}
        )

    def list_invoices(self, args=[]):
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            'account.invoice', 'search', [args]
        )

    def get_invoice(self, id: list):
        return self.models.execute_kw(
            self.db, self.uid, self.password, 'account.invoice', 'read', id)
