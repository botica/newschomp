from django import forms


class ArticleSearchForm(forms.Form):
    query = forms.CharField(
        max_length=200,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'hi',
            'class': 'search-input'
        })
    )
    source = forms.ChoiceField(
        choices=[
            ('apnews', 'AP News'),
            ('bbc', 'BBC News'),
        ],
        required=True,
        initial='apnews',
        widget=forms.Select(attrs={
            'class': 'source-select'
        })
    )
