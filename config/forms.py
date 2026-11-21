"""Shared form helpers so every form in the project looks the same."""

from django import forms


class FormStyleMixin:
    """Adds design-system CSS classes to every widget, plus an error class.

    Mix it in before forms.Form / forms.ModelForm:

        class MyForm(FormStyleMixin, forms.ModelForm):
            ...
    """

    #: Widgets that should not get the full-width .input treatment.
    bare_widgets = (
        forms.CheckboxInput,
        forms.RadioSelect,
        forms.CheckboxSelectMultiple,
        forms.FileInput,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            classes = widget.attrs.get('class', '').split()

            if not isinstance(widget, self.bare_widgets):
                classes.append('input')
            if self.is_bound and self.errors.get(name):
                classes.append('input-error')

            widget.attrs['class'] = ' '.join(dict.fromkeys(classes)).strip()
