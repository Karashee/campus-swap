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
        for field in self.fields.values():
            widget = field.widget
            if not isinstance(widget, self.bare_widgets):
                self._add_class(widget, 'input')

    def full_clean(self):
        """Mark the widgets that ended up with errors.

        This waits for validation instead of asking for self.errors in
        __init__: a formset adds its ORDER and DELETE fields just *after*
        building each form, so validating early would leave those fields out
        of cleaned_data entirely.
        """
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                self._add_class(self.fields[name].widget, 'input-error')

    @staticmethod
    def _add_class(widget, css_class):
        classes = widget.attrs.get('class', '').split()
        classes.append(css_class)
        # dict.fromkeys keeps the order and drops duplicates.
        widget.attrs['class'] = ' '.join(dict.fromkeys(classes)).strip()
