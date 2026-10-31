from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from Otoosin.whatsapp import send_template_message


class Command(BaseCommand):
    help = (
        "Send a labelled WhatsApp template test without creating or changing "
        "an order or payment. Recipients must be supplied explicitly with "
        "--to; the command never falls back to production admin recipients."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            action="append",
            dest="recipients",
            help=(
                "Recipient number in international or Nigerian local format; "
                "repeat for multiple test recipients."
            ),
        )
        parser.add_argument(
            "--parameter",
            action="append",
            dest="parameters",
            help="Template body parameter; repeat in Meta template order.",
        )
        parser.add_argument("--template", default=None)
        parser.add_argument("--language", default=None)

    def handle(self, *args, **options):
        recipients = options["recipients"] or []
        if not recipients:
            raise CommandError(
                "Provide at least one --to recipient. The test command never "
                "falls back to WHATSAPP_ADMIN_RECIPIENTS."
            )

        self.stdout.write(
            f"WhatsApp enabled: {bool(getattr(settings, 'WHATSAPP_ENABLED', False))}"
        )
        self.stdout.write(
            "Template: "
            f"{options['template'] or getattr(settings, 'WHATSAPP_MESSAGE_TEMPLATE', '') or '(missing)'}"
        )
        self.stdout.write(
            "Language: "
            f"{options['language'] or getattr(settings, 'WHATSAPP_TEMPLATE_LANGUAGE', '') or '(missing)'}"
        )

        parameters = options["parameters"] or [
            "O'Toosin Farms development WhatsApp test notification"
        ]
        failed = False
        for recipient in recipients:
            result = send_template_message(
                recipient,
                body_parameters=parameters,
                template_name=options["template"],
                language=options["language"],
            )
            if result.accepted:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Accepted by Meta for recipient ending "
                        f"{result.recipient[-4:]}; HTTP {result.status_code}; "
                        f"wamid {result.message_id}; delivery receipt is not implemented."
                    )
                )
            else:
                failed = True
                self.stderr.write(
                    self.style.ERROR(
                        f"WhatsApp test failed ({result.category}, HTTP "
                        f"{result.status_code}, code {result.error_code}, "
                        f"subcode {result.error_subcode}, trace "
                        f"{result.trace_id or 'n/a'}): {result.message}"
                    )
                )
        if failed:
            raise CommandError("One or more WhatsApp test messages were not accepted.")
