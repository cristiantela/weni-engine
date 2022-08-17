import stripe
import pendulum
from connect.celery import app
from connect.common.models import Organization, Project, BillingPlan
from connect.billing.models import (
    Contact,
    Message,
    SyncManagerTask,
    ContactCount,
    Channel,
)
from connect.elastic.flow import ElasticFlow
from django.utils import timezone
from connect import utils
from celery import current_app
from django.conf import settings


@app.task(
    name="get_messages",
    ignore_result=True
)
def get_messages(temp_channel_uuid: str, before: str, after: str, project_uuid: str):
    manager = SyncManagerTask.objects.create(
        task_type="get_messages",
        started_at=pendulum.now(),
        before=pendulum.parse(before),
        after=pendulum.parse(after)
    )

    flow_instance = utils.get_grpc_types().get("flow")
    project = Project.objects.get(uuid=project_uuid)
    contacts = Contact.objects.filter(channel__uuid=temp_channel_uuid, last_seen_on__range=(after, before))
    for contact in contacts:
        message = flow_instance.get_message(
            str(project.flow_organization), str(contact.contact_flow_uuid), before, after
        )

        if not message:
            last_message = Message.objects.filter(
                contact=contact,
                created_on__date__month=timezone.now().date().month,
                created_on__date__year=timezone.now().date().year,
            )

        if not last_message.exists():
            contact.delete()
            manager.fail_message.create(
                message="Contact don't have delivery/received message"
            )

            continue

        try:
            Message.objects.get(message_flow_uuid=message.uuid)
        except Message.DoesNotExist:
            Message.objects.create(
                contact=contact,
                text=message.text,
                created_on=message.created_on,
                direction=message.direction,
                message_flow_uuid=message.uuid,
            )

        channel = Channel.create(
            channel_type=message.channel_type,
            channel_flow_id=message.channel_id,
            project=project,
        )
        contact.update_channel(channel)

    count_contacts.apply_async(args=[manager.before, manager.after, project_uuid])

    return True


@app.task(name="create_contacts", ignore_result=True)
def create_contacts(active_contacts: list, project_uuid: Project):

    project = Project.objects.get(uuid=project_uuid)

    for elastic_contact in active_contacts:
        Contact.objects.create(
            contact_flow_uuid=elastic_contact["_source"].get("uuid"),
            name=elastic_contact["_source"].get("name"),
            last_seen_on=pendulum.parse(elastic_contact["_source"].get("last_seen_on")),
            project=project
        )


@app.task(name="sync_contacts", ignore_result=True)
def sync_contacts(
    sync_before: str = None, sync_after: str = None, task_uuid: str = None
):
    if sync_before and sync_after:
        sync_before = pendulum.parse(sync_before)
        sync_after = pendulum.parse(sync_after)
        manager = SyncManagerTask.objects.get(uuid=task_uuid)
    else:
        manager = SyncManagerTask.objects.create(
            task_type="sync_contacts",
            started_at=pendulum.now(),
            before=pendulum.now(),
            after=pendulum.now().subtract(hours=1),
        )

    try:
        elastic_instance = ElasticFlow()
        update_fields = ["finished_at", "status"]
        projects = Project.objects.exclude(flow_id=None)
        scroll = {}
        for project in projects:
            if scroll != {}:
                elastic_instance.clear_scroll(scroll_id=scroll["scroll_id"])
            scroll, active_contacts = list(
                elastic_instance.get_paginated_contacts(
                    str(project.flow_id), str(manager.before), str(manager.after)
                )
            )

            scrolled = 0

            while scrolled <= scroll["scroll_size"]:
                scrolled += len(active_contacts)

                create_contacts.apply_async(args=[active_contacts, str(project.uuid)])
                active_contacts = elastic_instance.get_paginated_contacts(
                    str(project.flow_id), str(manager.before), str(manager.after), scroll_id=scroll["scroll_id"]
                )
                if scrolled == scroll["scroll_size"]:
                    break

            count_contacts.apply_async(args=[manager.before, manager.after, project.uuid])

        manager.finished_at = timezone.now()
        manager.status = True
        manager.save(update_fields=update_fields)
        return manager.status
    except Exception as error:
        manager.finished_at = timezone.now()
        manager.fail_message.create(message=str(error))
        manager.status = False
        manager.save(update_fields=["finished_at", "status"])
        return False


@app.task(name="retry_billing_tasks")
def retry_billing_tasks():
    task_failed = SyncManagerTask.objects.filter(status=False, retried=False)

    for task in task_failed:
        task.retried = True
        task.save()

        if task.task_type == "sync_contacts":
            current_app.send_task(  # pragma: no cover
                name="sync_contacts", args=[task.before, task.after, task.uuid]
            )

    return True


@app.task(name="count_contacts", ignore_result=True)
def count_contacts(before, after, project_uuid: str, task_uuid: str = None):
    if task_uuid:
        manager = SyncManagerTask.objects.get(uuid=task_uuid)
    else:
        manager = SyncManagerTask.objects.create(
            task_type="count_contacts",
            started_at=pendulum.now(),
            before=before,
            after=after,
        )
    try:
        project = Project.objects.get(uuid=project_uuid)
        amount = project.contacts.filter(last_seen_on__range=(after, before)).count()
        now = pendulum.now()
        try:
            contact_count = ContactCount.objects.get(
                created_at__range=(now.start_of("day"), now.end_of("day")), project=project
            )
        except ContactCount.DoesNotExist:
            contact_count = ContactCount.objects.create(
                project=project,
                count=0
            )

        contact_count.increase_contact_count(amount)
        manager.status = True
        manager.finished_at = pendulum.now()
        manager.save(update_fields=["status", "finished_at"])
        return True
    except Exception as error:
        manager.finished_at = pendulum.now()
        manager.fail_message.create(message=str(error))
        manager.status = False
        manager.save(update_fields=["finished_at", "status"])
        return False


@app.task(name="refund_validation_charge")
def refund_validation_charge(charge_id):  # pragma: no cover
    stripe.api_key = settings.BILLING_SETTINGS.get("stripe", {}).get("API_KEY")
    stripe.Refund.create(charge=charge_id)
    return True


@app.task(name="problem_capture_invoice")
def problem_capture_invoice():
    for organization in Organization.objects.filter(
        organization_billing__plan=BillingPlan.PLAN_ENTERPRISE, is_suspended=False
    ):
        if organization.organization_billing.problem_capture_invoice:
            organization.is_suspended = True
            organization.save(update_fields=["is_suspended"])
            organization.organization_billing.is_active = False
            organization.organization_billing.save(update_fields=["is_active"])
            for project in organization.project.all():
                current_app.send_task(  # pragma: no cover
                    name="update_suspend_project",
                    args=[project.flow_organization, True],
                )


@app.task(name="sync_contacts_retroactive")
def sync_contacts_retroactive(before, after, task_uuid: str = None):  # pragma: no cover
    if task_uuid:
        manager = SyncManagerTask.objects.get(uuid=task_uuid)
    else:
        last_retroactive_sync = SyncManagerTask.objects.filter(
            task_type="retroactive_sync",
            status=True,
        ).order_by("started_at").last()

        if last_retroactive_sync:
            after = pendulum.instance(last_retroactive_sync.before)
            before = after.add(hours=3)

        manager = SyncManagerTask.objects.create(
            task_type="retroactive_sync",
            started_at=pendulum.now(),
            before=before,
            after=after
        )

    try:
        flow_instance = utils.get_grpc_types().get("flow")
        for project in Project.objects.exclude(flow_id=None):
            active_contacts = list(
                flow_instance.get_active_contacts(
                    str(project.flow_organization), str(before), str(after)))
            bulk_contacts = []
            for active_contact in active_contacts:
                ts = f"{active_contact.msg.sent_on.seconds.real}.{active_contact.msg.sent_on.nanos.real}"
                contact = Contact(
                    contact_flow_uuid=active_contact.uuid,
                    name=active_contact.name,
                    last_seen_on=pendulum.from_timestamp(float(ts)),
                    project=project,
                )
                bulk_contacts.append(contact)

            Contact.objects.bulk_create(bulk_contacts)
        manager.finished_at = pendulum.now()
        manager.status = True
        manager.save(update_fields=["finished_at", "status"])
    except Exception as error:
        manager.finished_at = pendulum.now()
        manager.fail_message.create(message=str(error))
        manager.status = False
        manager.save(update_fields=["finished_at", "status"])
        return False
