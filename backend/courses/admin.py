from django.contrib import admin

from .models import Course, Enrollment, Holiday, Meeting, Section, Term


class HolidayInline(admin.TabularInline):
    model = Holiday
    extra = 0


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ['name', 'instruction_begins', 'instruction_ends', 'finals_begin', 'finals_end']
    search_fields = ['name']
    inlines = [HolidayInline]


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'title', 'units']
    list_filter = ['subject']
    search_fields = ['subject', 'number', 'title']


class MeetingInline(admin.TabularInline):
    model = Meeting
    extra = 1


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ['course', 'section_code', 'crn', 'term', 'instructor', 'created_by']
    list_filter = ['term', 'course__subject']
    search_fields = ['crn', 'course__subject', 'course__number', 'course__title', 'instructor']
    autocomplete_fields = ['course', 'created_by']
    readonly_fields = ['created_by', 'created_at', 'updated_at']
    list_select_related = ['course', 'term', 'created_by']
    inlines = [MeetingInline]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ['user', 'section', 'created_at']
    list_filter = ['section__term']
    search_fields = ['user__username', 'section__crn', 'section__course__subject']
    autocomplete_fields = ['user', 'section']
