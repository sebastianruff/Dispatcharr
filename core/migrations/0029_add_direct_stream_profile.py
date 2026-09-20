# Add the built-in Direct stream profile and treat it as a UI opt-in.

from django.db import migrations

DIRECT_PROFILE_NAME = "Direct"
PROXY_PROFILE_NAME = "Proxy"
REDIRECT_PROFILE_NAME = "Redirect"


def add_direct_stream_profile(apps, schema_editor):
    StreamProfile = apps.get_model("core", "StreamProfile")
    UserAgent = apps.get_model("core", "UserAgent")

    if StreamProfile.objects.filter(name=DIRECT_PROFILE_NAME, locked=True).exists():
        return

    default_user_agent = (
        UserAgent.objects.filter(is_active=True)
        .order_by("id")
        .first()
    )

    StreamProfile.objects.create(
        name=DIRECT_PROFILE_NAME,
        command="",
        parameters="",
        is_active=True,
        locked=True,
        user_agent=default_user_agent,
    )


def remove_direct_stream_profile(apps, schema_editor):
    StreamProfile = apps.get_model("core", "StreamProfile")
    StreamProfile.objects.filter(name=DIRECT_PROFILE_NAME, locked=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0028_alter_systemevent_event_type"),
    ]

    operations = [
        migrations.RunPython(add_direct_stream_profile, remove_direct_stream_profile),
    ]
