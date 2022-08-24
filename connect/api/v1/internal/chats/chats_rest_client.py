from django.conf import settings

import requests

from connect.api.v1.internal.internal_authentication import InternalAuthentication


class ChatsRESTClient:
    def __init__(self):
        self.base_url = settings.CHATS_REST_ENDPOINT
        self.authentication_instance = InternalAuthentication()

    def update_user_permission(
        self, permission: int, user_email: str, project_uuid: str
    ):
        body = dict(role=permission, user=user_email, project=project_uuid)
        requests.put(
            url=f"{self.base_url}/v1/internal/permission/project/{project_uuid}/",
            headers=self.authentication_instance.headers,
            json=body,
        )
        return True

    def update_user_language(self, user_email: str, language: str):
        body = dict(user_email=user_email, language=language)
        requests.put(
            url=f"{self.base_url}/v1/internal/user/language/",
            headers=self.authentication_instance.headers,
            json=body,
        )
        return True

    def update_user(
        self,
        user_email: str,
        first_name: str = None,
        last_name: str = None,
        photo_url: str = None,
    ):
        body = dict(email=user_email)

        if first_name:
            body.update(dict(first_name=first_name))

        if last_name:
            body.update(dict(last_name=last_name))

        if photo_url:
            body.update(dict(photo_url=photo_url))

        requests.post(
            url=f"{self.base_url}/v1/internal/user/",
            headers=self.authentication_instance.headers,
            json=body,
        )

    def create_chat_project(
        self, project_uuid: str, project_name: str, date_format: str, timezone: str
    ):
        body = dict(
            uuid=project_uuid,
            name=project_name,
            date_format=date_format,
            timezone=timezone,
        )
        requests.post(
            url=f"{self.base_url}/v1/internal/project/",
            headers=self.authentication_instance.headers,
            json=body,
        )

    def delete_chat(self, project_uuid: str):
        requests.delete(
            url=f"{self.base_url}/v1/internal/project/{project_uuid}/",
            headers=self.authentication_instance.headers,
        )
