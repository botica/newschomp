from django import forms


class ArticleSearchForm(forms.Form):
    query = forms.CharField(
        max_length=200,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'Search AP News...',
            'class': 'search-input'
        })
    )
