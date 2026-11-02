import re

from django.db import migrations, models

from Otoosin.legal_defaults import DEFAULT_LEGAL_DOCUMENTS


def _clean(value):
    return (value or "").replace("&amp;", "&")


def _has_html(value):
    return "<p" in (value or "") or "<ul" in (value or "") or "<div" in (value or "")


def sync_legal_content(apps, schema_editor):
    LegalDocument = apps.get_model("Otoosin", "LegalDocument")
    LegalSection = apps.get_model("Otoosin", "LegalSection")

    for data in DEFAULT_LEGAL_DOCUMENTS.values():
        document = LegalDocument.objects.filter(slug=data["slug"]).first()
        if document is None:
            document = LegalDocument.objects.create(
                slug=data["slug"],
                title=_clean(data["title"]),
                eyebrow=_clean(data["eyebrow"]),
                intro=_clean(data["intro"]),
                lead=data["lead"],
                is_published=True,
            )
            replace_sections = True
        else:
            document.title = _clean(document.title)
            document.eyebrow = _clean(document.eyebrow)
            document.intro = _clean(document.intro)
            sections = list(document.sections.all())
            replace_sections = _has_html(document.lead) or any(
                _has_html(section.content) for section in sections
            )
            if not replace_sections:
                document.lead = _clean(document.lead)
            document.save()

        if replace_sections:
            document.title = _clean(data["title"])
            document.eyebrow = _clean(data["eyebrow"])
            document.intro = _clean(data["intro"])
            document.lead = data["lead"]
            document.save()
            document.sections.all().delete()
            LegalSection.objects.bulk_create(
                [
                    LegalSection(
                        document=document,
                        anchor=section["anchor"],
                        title=_clean(section["title"]),
                        content=section["content"],
                        sort_order=index,
                        is_callout=section.get("is_callout", False),
                    )
                    for index, section in enumerate(data["sections"])
                ]
            )
        else:
            callout_anchors = {
                section["anchor"]
                for section in data["sections"]
                if section.get("is_callout")
            }
            for section in document.sections.all():
                section.title = re.sub(
                    r"^\d+\.\s*", "", _clean(section.title)
                )
                section.content = _clean(section.content)
                section.is_callout = section.anchor in callout_anchors
                section.save(
                    update_fields=["title", "content", "is_callout"]
                )


class Migration(migrations.Migration):

    dependencies = [
        ("Otoosin", "0009_legaldocument_legalsection"),
    ]

    operations = [
        migrations.AddField(
            model_name="legalsection",
            name="is_callout",
            field=models.BooleanField(
                default=False,
                help_text="Display this section in a highlighted contact panel.",
            ),
        ),
        migrations.RunPython(sync_legal_content, migrations.RunPython.noop),
    ]
