"""Persistent top-5 leaderboard (SQLite via the Django ORM)."""
from django.db import models, transaction

LEADERBOARD_SIZE = 5


class LeaderboardEntry(models.Model):
    player_name = models.CharField(max_length=40)
    score = models.PositiveIntegerField()
    total_questions = models.PositiveIntegerField()
    percentage = models.FloatField()
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Rank: highest percentage, then highest score, then earliest completion.
        ordering = ["-percentage", "-score", "completed_at", "id"]
        verbose_name_plural = "leaderboard entries"
        constraints = [
            models.CheckConstraint(
                check=models.Q(score__lte=models.F("total_questions")), name="score_lte_total"
            ),
        ]

    def __str__(self):
        return f"{self.player_name}: {self.score}/{self.total_questions} ({self.percentage}%)"

    @classmethod
    def top(cls):
        return list(cls.objects.all()[:LEADERBOARD_SIZE])

    @classmethod
    def record(cls, player_name, score, total):
        """Save a result, then keep only the top LEADERBOARD_SIZE rows.

        Returns the new entry, or None if it did not make the cut.
        """
        with transaction.atomic():
            entry = cls.objects.create(
                player_name=player_name,
                score=score,
                total_questions=total,
                percentage=round(score * 100 / total, 2),
            )
            keep = list(cls.objects.values_list("pk", flat=True)[:LEADERBOARD_SIZE])
            cls.objects.exclude(pk__in=keep).delete()
            return entry if entry.pk in keep else None
