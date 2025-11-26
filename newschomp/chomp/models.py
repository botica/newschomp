from django.db import models
from django.utils import timezone

class Article(models.Model):
    title = models.CharField(max_length=255)
    pub_date = models.DateTimeField()
    url = models.URLField(max_length=500)
    content = models.TextField(null=True, blank=True)
    summary = models.TextField(null=True, blank=True)
    ai_title = models.CharField(max_length=100, null=True, blank=True)
    image_url = models.URLField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']
