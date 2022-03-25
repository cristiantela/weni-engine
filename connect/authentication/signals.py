import logging

from django.conf import settings
from django.db import models
from django.dispatch import receiver
from keycloak import exceptions

from connect.api.v1.keycloak import KeycloakControl
from connect.authentication.models import User

logger = logging.getLogger("connect.authentication.signals")


@receiver(models.signals.post_save, sender=User)
def signal_user(instance, created, **kwargs):
    if not settings.TESTING:
        try:
            keycloak_instance = KeycloakControl()

            user_id = keycloak_instance.get_user_id_by_email(email=instance.email)
            keycloak_instance.get_instance().update_user(
                user_id=user_id,
                payload={
                    "firstName": instance.first_name,
                    "lastName": instance.last_name,
                },
            )
        except exceptions.KeycloakGetError as e:
            logger.error(e)

    if created:
        from connect.common.models import (
            RequestPermissionOrganization,
            RequestPermissionProject,
        )

        requests_perm = RequestPermissionOrganization.objects.filter(
            email=instance.email
        )
        for perm in requests_perm:
            perm.organization.get_user_authorization(
                user=instance, defaults={"role": perm.role}
            )
        requests_perm.delete()

        requests_perm_project = RequestPermissionProject.objects.filter(
            email=instance.email
        )
        for perm in requests_perm_project:
            perm.project.get_user_authorization(
                user=instance, defaults={"role": perm.role}
            )
        requests_perm_project.delete()
