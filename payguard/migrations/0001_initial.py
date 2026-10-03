import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CardCooldown",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("account", "Account"),
                            ("ip", "Client IP"),
                            ("email", "Email"),
                            ("fingerprint", "Card fingerprint"),
                        ],
                        max_length=16,
                    ),
                ),
                ("key", models.CharField(max_length=255)),
                ("fail_count", models.PositiveIntegerField(default=0)),
                ("blocked_until", models.DateTimeField(blank=True, null=True)),
                ("first_fail_at", models.DateTimeField(blank=True, null=True)),
                ("last_fail_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "payguard_card_cooldowns",
                "unique_together": {("kind", "key")},
            },
        ),
        migrations.AddIndex(
            model_name="cardcooldown",
            index=models.Index(fields=["kind", "key"], name="payguard_ca_kind_1a2b3c_idx"),
        ),
        migrations.CreateModel(
            name="CardAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fingerprint", models.CharField(blank=True, db_index=True, max_length=255)),
                ("ip", models.CharField(blank=True, max_length=255)),
                ("email", models.CharField(blank=True, max_length=255)),
                ("outcome", models.CharField(default="failed", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payguard_card_attempts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "payguard_card_attempts",
            },
        ),
        migrations.AddIndex(
            model_name="cardattempt",
            index=models.Index(fields=["user", "created_at"], name="payguard_ca_user_id_4d5e6f_idx"),
        ),
        migrations.AddIndex(
            model_name="cardattempt",
            index=models.Index(fields=["fingerprint", "created_at"], name="payguard_ca_fingerp_7a8b9c_idx"),
        ),
    ]
