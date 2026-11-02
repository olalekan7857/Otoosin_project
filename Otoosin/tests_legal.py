from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError
from django.test import TestCase

from .models import AuditEvent, LegalDocument, LegalSection
from .permissions import provision_staff_roles


class LegalDocumentTests(TestCase):
    def setUp(self):
        provision_staff_roles()
        User = get_user_model()
        self.manager = User.objects.create_user(
            username="legal-manager",
            email="legal-manager@example.com",
            password="test-password",
            is_staff=True,
        )
        self.manager.groups.add(Group.objects.get(name="Manager"))
        self.support = User.objects.create_user(
            username="legal-support",
            email="legal-support@example.com",
            password="test-password",
            is_staff=True,
        )
        self.support.groups.add(Group.objects.get(name="Support"))

    def _payload(self, document, sections, *, published=True, title=None):
        prefix = f"document-{document.slug}"
        section_prefix = f"sections-{document.slug}"
        data = {
            "document": document.slug,
            f"{prefix}-title": title or document.title,
            f"{prefix}-eyebrow": document.eyebrow,
            f"{prefix}-intro": document.intro,
            f"{prefix}-lead": document.lead,
            f"{section_prefix}-TOTAL_FORMS": str(len(sections)),
            f"{section_prefix}-INITIAL_FORMS": str(
                len([section for section in sections if section.get("id")])
            ),
            f"{section_prefix}-MIN_NUM_FORMS": "0",
            f"{section_prefix}-MAX_NUM_FORMS": "1000",
        }
        if published:
            data[f"{prefix}-is_published"] = "on"
        for index, section in enumerate(sections):
            key = f"{section_prefix}-{index}"
            if section.get("id"):
                data[f"{key}-id"] = str(section["id"])
            data[f"{key}-sort_order"] = str(index)
            data[f"{key}-title"] = section.get("title", "")
            data[f"{key}-content"] = section.get("content", "")
            if section.get("is_callout"):
                data[f"{key}-is_callout"] = "on"
            if section.get("delete"):
                data[f"{key}-DELETE"] = "on"
        return data

    def _sections(self, document):
        return [
            {
                "id": section.pk,
                "title": section.title,
                "content": section.content,
                "is_callout": section.is_callout,
            }
            for section in document.sections.order_by("sort_order", "pk")
        ]

    def test_initial_documents_are_plain_text_and_keep_their_content(self):
        privacy = LegalDocument.objects.get(slug=LegalDocument.Slug.PRIVACY)
        terms = LegalDocument.objects.get(slug=LegalDocument.Slug.TERMS)
        self.assertEqual(privacy.sections.count(), 13)
        self.assertEqual(terms.sections.count(), 17)
        self.assertTrue(privacy.is_published)
        self.assertEqual(terms.title, "Terms & Conditions")
        self.assertFalse(privacy.sections.get(anchor="scope").title[0].isdigit())
        self.assertTrue(privacy.sections.get(anchor="contact").is_callout)

        response = self.client.get("/privacy/")
        self.assertContains(response, "Scope of this policy")
        self.assertContains(response, "1. Scope of this policy")
        self.assertContains(self.client.get("/terms/"), "About these terms")

    def test_terms_title_is_not_double_escaped(self):
        self.client.force_login(self.manager)
        response = self.client.get("/staff/legal/")
        self.assertContains(response, "Save Terms &amp; Conditions")
        self.assertNotContains(response, "&amp;amp;")
        self.assertNotContains(self.client.get("/terms/"), "&amp;amp;")

    def test_anonymous_and_unauthorized_staff_cannot_edit(self):
        self.assertRedirects(
            self.client.get("/staff/legal/"),
            "/staff/login/?next=/staff/legal/",
            fetch_redirect_response=False,
        )
        self.client.force_login(self.support)
        self.assertEqual(self.client.get("/staff/legal/").status_code, 403)

    def test_authorized_staff_can_update_a_subsection(self):
        self.client.force_login(self.manager)
        privacy = LegalDocument.objects.get(slug="privacy")
        sections = self._sections(privacy)
        sections[0]["content"] = "The updated privacy subsection."

        response = self.client.post(
            "/staff/legal/",
            self._payload(
                privacy,
                sections,
                title="Updated Privacy Policy",
            ),
        )

        self.assertRedirects(response, "/staff/legal/#legal-privacy")
        privacy.refresh_from_db()
        self.assertEqual(privacy.title, "Updated Privacy Policy")
        self.assertEqual(
            privacy.sections.get(anchor="scope").content,
            "The updated privacy subsection.",
        )
        page = self.client.get("/privacy/")
        self.assertContains(page, "The updated privacy subsection.")
        self.assertContains(page, "1. Scope of this policy")
        self.assertTrue(
            AuditEvent.objects.filter(
                action="legal_document_updated",
                target_id=str(privacy.pk),
            ).exists()
        )

    def test_sections_can_be_added_and_removed_without_breaking_numbering(self):
        self.client.force_login(self.manager)
        privacy = LegalDocument.objects.get(slug="privacy")
        sections = self._sections(privacy)
        sections.append(
            {
                "title": "New owner-approved section",
                "content": "A newly added section.",
            }
        )

        response = self.client.post(
            "/staff/legal/", self._payload(privacy, sections)
        )
        self.assertRedirects(response, "/staff/legal/#legal-privacy")
        new_section = privacy.sections.get(title="New owner-approved section")
        self.assertTrue(new_section.anchor)
        self.assertEqual(new_section.sort_order, len(sections) - 1)
        page = self.client.get("/privacy/")
        self.assertContains(page, f"{len(sections)}. New owner-approved section")

        sections = self._sections(privacy)
        first_title = sections[1]["title"]
        sections[0]["delete"] = True
        response = self.client.post(
            "/staff/legal/", self._payload(privacy, sections)
        )
        self.assertRedirects(response, "/staff/legal/#legal-privacy")
        self.assertFalse(privacy.sections.filter(anchor="scope").exists())
        page = self.client.get("/privacy/")
        self.assertContains(page, f"1. {first_title}")

    def test_sections_can_be_reordered(self):
        self.client.force_login(self.manager)
        privacy = LegalDocument.objects.get(slug="privacy")
        sections = self._sections(privacy)
        last_title = sections[-1]["title"]
        sections.reverse()

        response = self.client.post(
            "/staff/legal/", self._payload(privacy, sections)
        )
        self.assertRedirects(response, "/staff/legal/#legal-privacy")
        page = self.client.get("/privacy/")
        self.assertContains(page, f"1. {last_title}")
        self.assertEqual(
            privacy.sections.order_by("sort_order").first().title,
            last_title,
        )

    def test_unpublished_document_is_not_exposed(self):
        self.client.force_login(self.manager)
        privacy = LegalDocument.objects.get(slug="privacy")
        sections = self._sections(privacy)
        sections[0]["content"] = "Private draft content."

        response = self.client.post(
            "/staff/legal/",
            self._payload(privacy, sections, published=False),
        )
        self.assertRedirects(response, "/staff/legal/#legal-privacy")
        privacy.refresh_from_db()
        self.assertFalse(privacy.is_published)
        self.assertEqual(self.client.get("/privacy/").status_code, 404)
        self.assertNotContains(
            self.client.get("/"),
            'href="/privacy/"',
        )
        self.assertNotContains(
            self.client.get("/terms/"),
            "Private draft content.",
        )

    def test_missing_document_is_handled_gracefully(self):
        LegalDocument.objects.filter(slug="privacy").delete()
        self.assertEqual(self.client.get("/privacy/").status_code, 404)
        self.client.force_login(self.manager)
        response = self.client.get("/staff/legal/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Terms &amp; Conditions")

    def test_body_markup_is_escaped_instead_of_rendered(self):
        self.client.force_login(self.manager)
        privacy = LegalDocument.objects.get(slug="privacy")
        sections = self._sections(privacy)
        sections[0]["content"] = '<script>alert(1)</script>'

        self.client.post(
            "/staff/legal/", self._payload(privacy, sections)
        )
        page = self.client.get("/privacy/")
        self.assertContains(page, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(page, "<script>alert(1)</script>")
        self.assertEqual(
            privacy.sections.get(anchor="scope").content,
            '<script>alert(1)</script>',
        )

    def test_footer_links_only_show_published_documents(self):
        home = self.client.get("/")
        self.assertContains(home, 'href="/privacy/"')
        self.assertContains(home, 'href="/terms/"')
        self.assertContains(home, "Privacy Policy")
        self.assertContains(home, "Terms &amp; Conditions")

        LegalDocument.objects.filter(slug="terms").update(is_published=False)
        home = self.client.get("/")
        self.assertNotContains(home, 'href="/terms/"')
        self.assertContains(home, 'href="/privacy/"')

    def test_anchor_uniqueness_is_enforced(self):
        privacy = LegalDocument.objects.get(slug="privacy")
        with self.assertRaises(IntegrityError):
            LegalSection.objects.create(
                document=privacy,
                anchor="scope",
                title="Duplicate",
                content="Duplicate anchor",
            )

    def test_public_page_reflects_saved_change_without_restart(self):
        self.client.force_login(self.manager)
        privacy = LegalDocument.objects.get(slug="privacy")
        sections = self._sections(privacy)
        sections[1]["content"] = "A changed paragraph for the live page."
        self.client.post("/staff/legal/", self._payload(privacy, sections))
        self.assertContains(
            self.client.get("/privacy/"),
            "A changed paragraph for the live page.",
        )
