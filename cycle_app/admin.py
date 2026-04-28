from django.contrib import admin
from .models import CycleRecord

@admin.register(CycleRecord)
class CycleRecordAdmin(admin.ModelAdmin):
    list_display = ('date', 'flow_intensity', 'notes')
    search_fields = ('date',)
    list_filter = ('flow_intensity',)