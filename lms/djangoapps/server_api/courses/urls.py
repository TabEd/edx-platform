"""
Courses API URI specification
The order of the URIs really matters here, due to the slash characters present in the identifiers
"""
from django.conf import settings
from django.conf.urls import patterns, url
from rest_framework.urlpatterns import format_suffix_patterns

from server_api.courses import views as courses_views


CONTENT_ID_PATTERN = r'(?P<content_id>[\.a-zA-Z0-9_+\/:-]+)'
TAB_ID_PATTERN = r'(?P<tab_id>[a-zA-Z0-9_+\/:-]+)'
COURSE_ID_PATTERN = settings.COURSE_ID_PATTERN

URLS = [
    ('content', courses_views.CourseContentList, 'content_list'),
    # Note: The child pattern must come first; otherwise, the content_id pattern will need to be modified to filter out the word children.
    ('content/{content_id_pattern}/children', courses_views.CourseContentList, 'content_children_list'),
    ('content/{content_id_pattern}', courses_views.CourseContentDetail, 'content_detail'),
    ('overview', courses_views.CoursesOverview, 'overview'),
    ('static_tabs', courses_views.CoursesStaticTabsList, 'static_tabs_list'),
    ('static_tabs/{tab_id_pattern}', courses_views.CoursesStaticTabsDetail, 'static_tabs_detail'),
    ('updates', courses_views.CoursesUpdates, 'updates'),
]

# pylint: disable=invalid-name
api_patterns = [
    url(r'^$', courses_views.CoursesList.as_view(), name='list'),
    url(r'^{course_id_pattern}/$'.format(course_id_pattern=COURSE_ID_PATTERN), courses_views.CoursesDetail.as_view(),
        name='detail')
]

for path, view, name in URLS:
    path = path.format(content_id_pattern=CONTENT_ID_PATTERN, tab_id_pattern=TAB_ID_PATTERN)
    regex = r'^{course_id_pattern}/{path}/$'.format(course_id_pattern=COURSE_ID_PATTERN, path=path)
    api_patterns.append(url(regex, view.as_view(), name=name))

urlpatterns = patterns(
    '',
    *api_patterns
)

urlpatterns = format_suffix_patterns(urlpatterns)
