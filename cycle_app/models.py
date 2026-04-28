from django.db import models

class CycleRecord(models.Model):
    date = models.DateField()
    flow_intensity = models.CharField(max_length=10, choices=[('light', 'Легкий'), ('heavy', 'Обильный')])
    notes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = 'Запись о цикле'
        verbose_name_plural = 'Записи о цикле'
    
    def __str__(self):
        return f"{self.date} - {self.flow_intensity}"