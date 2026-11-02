import re

from django.db import migrations


def join_list_blocks(apps, schema_editor):
    LegalSection = apps.get_model("Otoosin", "LegalSection")
    for section in LegalSection.objects.all().iterator():
        content = section.content or ""
        fixed = re.sub(r"\n\n(?=(?:- |\* |\d+[.)] ))", "\n", content)
        if fixed != content:
            section.content = fixed
            section.save(update_fields=["content"])


class Migration(migrations.Migration):

    dependencies = [
        ("Otoosin", "0010_legal_plain_text_content"),
    ]

    operations = [
        migrations.RunPython(join_list_blocks, migrations.RunPython.noop),
    ]
