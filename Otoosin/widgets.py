from django import forms


class AdminImageInput(forms.ClearableFileInput):
    template_name = "admin/widgets/admin_image_input.html"
