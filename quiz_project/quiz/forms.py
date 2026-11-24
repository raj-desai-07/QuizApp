import re

from django import forms


class AnswerForm(forms.Form):
    """Validates a submitted answer. Only the option index is accepted."""

    position = forms.IntegerField(
        min_value=0,
        error_messages={"required": "Invalid request.", "invalid": "Invalid request."},
    )
    choice = forms.IntegerField(
        min_value=0,
        error_messages={
            "required": "Please select an answer.",
            "invalid": "Please select a valid answer.",
            "min_value": "Please select a valid answer.",
        },
    )

    def __init__(self, *args, option_count, **kwargs):
        super().__init__(*args, **kwargs)
        self.option_count = option_count

    def clean_choice(self):
        choice = self.cleaned_data["choice"]
        if choice >= self.option_count:
            raise forms.ValidationError("Please select a valid answer.")
        return choice


class PlayerForm(forms.Form):
    """Validates the player name entered on the home page."""

    MAX_LENGTH = 40

    player_name = forms.CharField(
        max_length=MAX_LENGTH,
        strip=True,
        error_messages={
            "required": "Please enter your name to start the quiz.",
            "max_length": f"Name must be {MAX_LENGTH} characters or fewer.",
        },
    )

    def clean_player_name(self):
        name = re.sub(r"\s+", " ", self.cleaned_data["player_name"]).strip()
        if not name:
            raise forms.ValidationError("Please enter your name to start the quiz.")
        if any(not ch.isprintable() for ch in name):
            raise forms.ValidationError("Name contains invalid characters.")
        if not any(ch.isalnum() for ch in name):
            raise forms.ValidationError("Name must contain at least one letter or number.")
        return name
