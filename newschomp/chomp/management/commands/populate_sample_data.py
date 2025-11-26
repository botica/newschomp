from django.core.management.base import BaseCommand
from django.utils import timezone
from chomp.models import Article
from datetime import timedelta


class Command(BaseCommand):
    help = 'Populate database with sample articles'

    def handle(self, *args, **kwargs):
        # Clear existing articles
        Article.objects.all().delete()

        sample_articles = [
            {
                'title': 'Scientists Discover New Species of Deep-Sea Fish',
                'url': 'https://example.com/deep-sea-discovery',
                'pub_date': timezone.now() - timedelta(hours=2),
                'content': '<article><h1>Scientists Discover New Species of Deep-Sea Fish</h1><p>Marine biologists have discovered a bioluminescent fish species at depths of 3,000 meters in the Pacific Ocean. The creature exhibits unique adaptive features including translucent skin and oversized eyes.</p></article>',
                'summary': 'Marine biologists discovered a new bioluminescent fish species at 3,000 meters depth in the Pacific, featuring translucent skin and oversized eyes adapted to extreme deep-sea conditions.'
            },
            {
                'title': 'Tech Giant Announces Revolutionary AI Chip',
                'url': 'https://example.com/ai-chip-announcement',
                'pub_date': timezone.now() - timedelta(hours=5),
                'content': '<article><h1>Tech Giant Announces Revolutionary AI Chip</h1><p>A major technology company unveiled a groundbreaking AI processor promising 10x performance improvements while using 50% less power than current generation chips.</p></article>',
                'summary': 'Major tech company unveiled a revolutionary AI processor delivering 10x performance boost with 50% reduced power consumption compared to current generation chips.'
            },
            {
                'title': 'City Council Approves New Green Energy Initiative',
                'url': 'https://example.com/green-energy-plan',
                'pub_date': timezone.now() - timedelta(hours=8),
                'content': '<article><h1>City Council Approves New Green Energy Initiative</h1><p>The city council voted unanimously to implement solar panels on all municipal buildings by 2026, expected to reduce carbon emissions by 40%.</p></article>',
                'summary': 'City council unanimously approved installing solar panels on all municipal buildings by 2026, projected to cut carbon emissions by 40% and save taxpayer money.'
            },
            {
                'title': 'Local Restaurant Wins International Culinary Award',
                'url': 'https://example.com/restaurant-award',
                'pub_date': timezone.now() - timedelta(hours=12),
                'content': '<article><h1>Local Restaurant Wins International Culinary Award</h1><p>Downtown eatery "The Blue Plate" received the prestigious Golden Spoon award for its innovative fusion cuisine combining traditional techniques with modern flavors.</p></article>',
                'summary': 'Downtown restaurant The Blue Plate won prestigious Golden Spoon award for innovative fusion cuisine blending traditional cooking techniques with contemporary flavors.'
            },
            {
                'title': 'Study Reveals Coffee May Improve Memory Function',
                'url': 'https://example.com/coffee-memory-study',
                'pub_date': timezone.now() - timedelta(hours=18),
                'content': '<article><h1>Study Reveals Coffee May Improve Memory Function</h1><p>Researchers at a leading university found that moderate coffee consumption (2-3 cups daily) correlates with improved long-term memory retention in adults over 50.</p></article>',
                'summary': 'University research found moderate coffee consumption of 2-3 cups daily linked to enhanced long-term memory retention in adults over age 50.'
            },
            {
                'title': 'Rare Meteorite Found in Rural Farmland',
                'url': 'https://example.com/meteorite-discovery',
                'pub_date': timezone.now() - timedelta(days=1),
                'content': '<article><h1>Rare Meteorite Found in Rural Farmland</h1><p>A farmer discovered a 15-pound meteorite estimated to be 4.5 billion years old while plowing fields. Scientists believe it contains rare minerals not found on Earth.</p></article>',
                'summary': 'Farmer unearthed a 15-pound, 4.5-billion-year-old meteorite containing rare non-terrestrial minerals while plowing rural farmland fields.'
            },
            {
                'title': 'New Study Links Urban Green Spaces to Mental Health',
                'url': 'https://example.com/green-spaces-mental-health',
                'pub_date': timezone.now() - timedelta(days=1, hours=6),
                'content': '<article><h1>New Study Links Urban Green Spaces to Mental Health</h1><p>A 10-year study tracking 50,000 participants found that people living within walking distance of parks reported 25% lower anxiety and depression levels.</p></article>',
                'summary': 'Decade-long study of 50,000 participants revealed people living near parks experienced 25% lower rates of anxiety and depression.'
            },
            {
                'title': 'Archaeological Team Uncovers Ancient Trading Post',
                'url': 'https://example.com/ancient-trading-post',
                'pub_date': timezone.now() - timedelta(days=2),
                'content': '<article><h1>Archaeological Team Uncovers Ancient Trading Post</h1><p>Excavators discovered a 2,000-year-old trading hub containing pottery, coins, and trade goods from three different civilizations, suggesting extensive ancient commerce networks.</p></article>',
                'summary': 'Archaeologists unearthed 2,000-year-old trading hub with pottery, coins, and goods from three civilizations, revealing extensive ancient commerce networks.'
            },
        ]

        created_count = 0
        for article_data in sample_articles:
            Article.objects.create(**article_data)
            created_count += 1

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {created_count} sample articles')
        )
