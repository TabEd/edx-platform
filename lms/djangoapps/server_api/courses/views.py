""" API implementation for course-oriented interactions. """

from collections import OrderedDict
import logging
from lxml import etree
from StringIO import StringIO

from django.core.urlresolvers import reverse
from rest_framework import status
from rest_framework.response import Response

from courseware.courses import get_course_about_section, get_course_info_section, course_image_url
from courseware.views import get_static_tab_contents
from server_api.util.courseware_access import get_course, get_course_child, get_course_key, \
    get_modulestore, get_course_descriptor
from server_api.util.permissions import SecureAPIView, SecureListAPIView
from server_api.util.utils import generate_base_uri
from server_api.courses.serializers import CourseSerializer


log = logging.getLogger(__name__)


def _get_content_children(content, content_type=None):
    """
    Parses the provided content object looking for children
    Matches on child content type (category) when specified
    """
    children = []
    if hasattr(content, 'children'):
        child_content = content.get_children()
        for child in child_content:
            if content_type:
                if getattr(child, 'category') == content_type:
                    children.append(child)
            else:
                children.append(child)
    return children


def _serialize_content(request, course_key, content_descriptor):
    """
    Loads the specified content object into the response dict
    This should probably evolve to use DRF serializers
    """
    protocol = 'http'
    if request.is_secure():
        protocol += 's'

    server_uri = '{}://{}'.format(
        protocol,
        request.get_host()
    )

    data = {}

    if hasattr(content_descriptor, 'display_name'):
        data['name'] = content_descriptor.display_name

    if hasattr(content_descriptor, 'due'):
        data['due'] = content_descriptor.due

    data['start'] = getattr(content_descriptor, 'start', None)
    data['end'] = getattr(content_descriptor, 'end', None)

    data['category'] = content_descriptor.location.category

    # Some things we only do if the content object is a course
    if hasattr(content_descriptor, 'category') and content_descriptor.category == 'course':
        content_id = unicode(content_descriptor.id)
        content_uri = '{}{}'.format(server_uri, reverse('server_api:courses:detail', kwargs={'course_id': content_id}))
        data['number'] = content_descriptor.location.course
        data['org'] = content_descriptor.location.org

    # Other things we do only if the content object is not a course
    else:
        content_id = unicode(content_descriptor.location)
        # Need to use the CourseKey here, which will possibly result in a different (but valid)
        # URI due to the change in key formats during the "opaque keys" transition
        content_uri = '{}{}'.format(server_uri, reverse('server_api:courses:content_detail',
                                                        kwargs={'course_id': unicode(course_key),
                                                                'content_id': content_id}))

    data['id'] = unicode(content_id)
    data['uri'] = content_uri

    # Include any additional fields requested by the caller
    include_fields = request.QUERY_PARAMS.get('include_fields', None)
    if include_fields:
        include_fields = include_fields.split(',')
        for field in include_fields:
            data[field] = getattr(content_descriptor, field, None)

    return data


def _serialize_content_children(request, course_key, children):
    """
    Loads the specified content child data into the response dict
    This should probably evolve to use DRF serializers
    """
    data = []
    if children:
        for child in children:
            child_data = _serialize_content(
                request,
                course_key,
                child
            )
            data.append(child_data)
    return data


def _serialize_content_with_children(request, course_key, descriptor, depth):  # pylint: disable=C0103
    """
    Serializes course content and then dives into the content tree,
    serializing each child module until specified depth limit is hit
    """
    data = _serialize_content(
        request,
        course_key,
        descriptor
    )
    if depth > 0:
        data['children'] = []
        for child in descriptor.get_children():
            data['children'].append(_serialize_content_with_children(
                request,
                course_key,
                child,
                depth - 1
            ))
    return data


def _inner_content(tag):
    """
    Helper method
    """
    inner_content = None
    if tag is not None:
        inner_content = tag.text if tag.text else u''
        inner_content += u''.join(etree.tostring(e) for e in tag)
        inner_content += tag.tail if tag.tail else u''

    return inner_content


def _parse_updates_html(html):
    """
    Helper method to extract updates contained within the course info HTML into components
    Updates content is stored in MongoDB (aka, the module store) with the following naming convention

            {
                "_id.org":"i4x",
                "_id.course":<course_num>,
                "_id.category":"course_info",
                "_id.name":"updates"
            }
    """

    parser = etree.HTMLParser()
    tree = etree.parse(StringIO(html), parser)

    # get all of the individual postings
    postings = tree.findall('/body/section/article')

    # be backwards compatible
    if not postings:
        postings = tree.findall('/body/ol/li')

    result = []
    for posting in postings:
        posting_data = {}
        posting_date_element = posting.find('h2')
        if posting_date_element is not None:
            posting_data['date'] = posting_date_element.text

        content = u''
        for current_element in posting:
            # note, we can't delete or skip over the date element in
            # the HTML tree because there might be some tailing content
            if current_element != posting_date_element:
                content += etree.tostring(current_element)
            else:
                content += current_element.tail if current_element.tail else u''

        posting_data['content'] = content.strip()
        result.append(posting_data)

    return result


def _get_course_data(request, course_key, course_descriptor, depth=0):
    """
    creates a dict of course attributes
    """

    if depth > 0:
        data = _serialize_content_with_children(
            request,
            course_key,
            course_descriptor,  # Primer for recursive function
            depth
        )
        data['content'] = data['children']
        data.pop('children')
    else:
        data = _serialize_content(
            request,
            course_key,
            course_descriptor
        )
    base_uri_without_qs = generate_base_uri(request, True)
    if unicode(course_descriptor.id) not in base_uri_without_qs:
        base_uri_without_qs = '{}/{}'.format(base_uri_without_qs, unicode(course_descriptor.id))
    image_url = ''
    if hasattr(course_descriptor, 'course_image') and course_descriptor.course_image:
        image_url = course_image_url(course_descriptor)
    data['course_image_url'] = image_url

    resources = ['content', 'overview', 'updates', 'static_tabs']
    data['resources'] = [{'uri': '{}{}/'.format(base_uri_without_qs, resource)} for resource in resources]
    return data


class CourseContentList(SecureAPIView):
    """
    **Use Case**

        CourseContentList gets a collection of content for a given
        course. You can use the **uri** value in
        the response to get details for that content entity.

        CourseContentList has an optional type parameter that allows you to
        filter the response by content type. The value of the type parameter
        matches the category value in the response. Valid values for the type
        parameter are:

        * chapter
        * sequential
        * vertical
        * html
        * problem
        * discussion
        * video
        * [CONFIRM]

    **Example requests**:

        GET /api/courses/{course_id}/content

        GET /api/courses/{course_id}/content?type=video

        GET /api/courses/{course_id}/content/{content_id}/children

    **Response Values**

        * category: The type of content.

        * due: The due date.

        * uri: The URI to use to get details of the content entity.

        * id: The unique identifier for the content entity.

        * name: The name of the course.
    """

    def get(self, request, course_id, content_id=None):
        """
        GET /api/courses/{course_id}/content
        """
        user = request.user
        course_descriptor, course_key, _course_content = get_course(request, user, course_id)
        if not course_descriptor:
            return Response({}, status=status.HTTP_404_NOT_FOUND)
        if content_id is None:
            content_id = course_id
        response_data = []
        content_type = request.QUERY_PARAMS.get('type', None)
        if course_id != content_id:
            _content_descriptor, _content_key, content = get_course_child(request, user, course_key, content_id,
                                                                          load_content=True)
        else:
            content = course_descriptor
        if content:
            children = _get_content_children(content, content_type)
            response_data = _serialize_content_children(
                request,
                course_key,
                children
            )
            status_code = status.HTTP_200_OK
        else:
            status_code = status.HTTP_404_NOT_FOUND
        return Response(response_data, status=status_code)


class CourseContentDetail(SecureAPIView):
    """
    **Use Case**

        CourseContentDetail returns a JSON collection for a specified
        CourseContent entity. If the specified CourseContent is the Course, the
        course representation is returned. You can use the uri values in the
        children collection in the JSON response to get details for that content
        entity.

        CourseContentDetail has an optional type parameter that allows you to
        filter the response by content type. The value of the type parameter
        matches the category value in the response. Valid values for the type
        parameter are:

        * chapter
        * sequential
        * vertical
        * html
        * problem
        * discussion
        * video
        * [CONFIRM]

    **Example Request**

          GET /api/courses/{course_id}/content/{content_id}

    **Response Values**

        * category: The type of content.

        * name: The name of the content entity.

        * due:  The due date.

        * uri: The URI of the content entity.

        * id: The unique identifier for the course.

        * children: Content entities that this content entity contains.
    """

    def get(self, request, course_id, content_id):
        """
        GET /api/courses/{course_id}/content/{content_id}
        """
        course_descriptor, course_key, _course_content = get_course(request, request.user, course_id)
        response_data = {}
        base_uri = generate_base_uri(request)
        response_data['uri'] = base_uri
        if course_id != content_id:
            element_name = 'children'
            _content_descriptor, _content_key, course_descriptor = get_course_child(request, request.user, course_key, content_id, load_content=True)
        else:
            element_name = 'content'
            protocol = 'http'
            if request.is_secure():
                protocol += 's'
            response_data['uri'] = '{}://{}/api/server/courses/{}'.format(
                protocol,
                request.get_host(),
                unicode(course_key)
            )
        if not course_descriptor:
            return Response(response_data, status=status.HTTP_404_NOT_FOUND)
        response_data = _serialize_content(
            request,
            course_id,
            course_descriptor
        )
        content_type = request.QUERY_PARAMS.get('type', None)
        children = _get_content_children(course_descriptor, content_type)
        response_data[element_name] = _serialize_content_children(
            request,
            course_id,
            children
        )
        base_uri_without_qs = generate_base_uri(request, True)
        resource_uri = '{}/groups'.format(base_uri_without_qs)
        response_data['resources'] = []
        response_data['resources'].append({'uri': resource_uri})
        resource_uri = '{}/users'.format(base_uri_without_qs)
        response_data['resources'].append({'uri': resource_uri})
        return Response(response_data, status=status.HTTP_200_OK)


class CoursesList(SecureListAPIView):
    """
    **Use Case**

        CoursesList returns paginated list of courses in the edX Platform. You can
        use the uri value in the response to get details of the course. course list can be
        filtered by course_id

    **Example Request**

          GET /api/courses
          GET /api/courses/?course_id={course_id1},{course_id2}

    **Response Values**

        * category: The type of content. In this case, the value is always "course".

        * name: The name of the course.

        * uri: The URI to use to get details of the course.

        * number: The course number.

        * due:  The due date. For courses, the value is always null.

        * org: The organization specified for the course.

        * id: The unique identifier for the course.
    """
    serializer_class = CourseSerializer

    def get_queryset(self):
        course_ids = self.request.QUERY_PARAMS.get('course_id', None)
        depth = self.request.QUERY_PARAMS.get('depth', 0)
        course_descriptors = []
        if course_ids:
            course_ids = course_ids.split(',')
            for course_id in course_ids:
                course_key = get_course_key(course_id)
                course_descriptor = get_course_descriptor(course_key, 0)
                course_descriptors.append(course_descriptor)
        else:
            course_descriptors = get_modulestore().get_courses()

        results = [_get_course_data(self.request, descriptor.id, descriptor, depth)
                   for descriptor in course_descriptors]
        return results


class CoursesDetail(SecureAPIView):
    """
    **Use Case**

        CoursesDetail returns details for a course. You can use the uri values
        in the resources collection in the response to get more course
        information for:

        * Users (/api/courses/{course_id}/users/)
        * Groups (/api/courses/{course_id}/groups/)
        * Course Overview (/api/courses/{course_id}/overview/)
        * Course Updates (/api/courses/{course_id}/updates/)
        * Course Pages (/api/courses/{course_id}/static_tabs/)

        CoursesDetail has an optional **depth** parameter that allows you to
        get course content children to the specified tree level.

    **Example requests**:

        GET /api/courses/{course_id}

        GET /api/courses/{course_id}?depth=2

    **Response Values**

        * category: The type of content.

        * name: The name of the course.

        * uri: The URI to use to get details of the course.

        * number: The course number.

        * content: When the depth parameter is used, a collection of child
          course content entities, such as chapters, sequentials, and
          components.

        * due:  The due date. For courses, the value is always null.

        * org: The organization specified for the course.

        * id: The unique identifier for the course.

        * resources: A collection of URIs to use to get more information about
          the course.
    """

    def get(self, request, course_id):
        """
        GET /api/courses/{course_id}
        """
        depth = request.QUERY_PARAMS.get('depth', 0)
        depth_int = int(depth)
        # get_course_by_id raises an Http404 if the requested course is invalid
        # Rather than catching it, we just let it bubble up
        course_descriptor, course_key, _course_content = get_course(request, request.user, course_id, depth=depth_int)
        if not course_descriptor:
            return Response({}, status=status.HTTP_404_NOT_FOUND)
        response_data = _get_course_data(request, course_key, course_descriptor, depth_int)
        return Response(response_data, status=status.HTTP_200_OK)


class CoursesOverview(SecureAPIView):
    """
    **Use Case**

        CoursesOverview returns an HTML representation of the overview for the
        specified course. CoursesOverview has an optional parse parameter that
        when true breaks the response into a collection named sections. By
        default, parse is false.

    **Example Request**

          GET /api/courses/{course_id}/overview

          GET /api/courses/{course_id}/overview?parse=true

    **Response Values**

        * overview_html: The HTML representation of the course overview.
          Sections of the overview are indicated by an HTML section element.

        * sections: When parse=true, a collection of JSON objects representing
          parts of the course overview.

    """

    def get(self, request, course_id):
        """
        GET /api/courses/{course_id}/overview
        """
        response_data = OrderedDict()
        course_descriptor, _course_key, _course_content = get_course(request, request.user, course_id)
        if not course_descriptor:
            return Response({}, status=status.HTTP_404_NOT_FOUND)
        existing_content = get_course_about_section(course_descriptor, 'overview')
        if not existing_content or not len(existing_content):
            return Response({}, status=status.HTTP_404_NOT_FOUND)
        else:
            response_data['overview_html'] = existing_content
        image_url = ''
        if hasattr(course_descriptor, 'course_image') and course_descriptor.course_image:
            image_url = course_image_url(course_descriptor)
        response_data['course_image_url'] = image_url
        response_data['course_video'] = get_course_about_section(course_descriptor, 'video')
        return Response(response_data, status=status.HTTP_200_OK)


class CoursesUpdates(SecureAPIView):
    """
    **Use Case**

        CoursesUpdates returns an HTML representation of the overview for the
        specified course. CoursesUpdates has an optional parse parameter that
        when true breaks the response into a collection named postings. By
        default, parse is false.

    **Example Requests**

          GET /api/courses/{course_id}/updates

          GET /api/courses/{course_id}/updates?parse=true

    **Response Values**

        * content: The HTML representation of the course overview.
          Sections of the overview are indicated by an HTML section element.

        * postings: When parse=true, a collection of JSON objects representing
          parts of the course overview. Each element in postings contains a date
          and content key.
    """

    def get(self, request, course_id):
        """
        GET /api/courses/{course_id}/updates
        """
        course_descriptor, _course_key, _course_content = get_course(request, request.user, course_id)
        if not course_descriptor:
            return Response({}, status=status.HTTP_404_NOT_FOUND)
        response_data = OrderedDict()
        content = get_course_info_section(request, course_descriptor, 'updates')
        if not content:
            return Response({}, status=status.HTTP_404_NOT_FOUND)
        if request.GET.get('parse') and request.GET.get('parse') in ['True', 'true']:
            response_data['postings'] = _parse_updates_html(content)
        else:
            response_data['content'] = content
        return Response(response_data)


class CoursesStaticTabsList(SecureAPIView):
    """
    **Use Case**

        CoursesStaticTabsList returns a collection of custom pages in the
        course. CoursesStaticTabsList has an optional detail parameter that when
        true includes the custom page content in the response.

    **Example Requests**

          GET /api/courses/{course_id}/static_tabs

          GET /api/courses/{course_id}/static_tabs?detail=true

    **Response Values**

        * tabs: The collection of custom pages in the course. Each object in the
          collection conains the following keys:

          * id: The ID of the custom page.

          * name: The Display Name of the custom page.

          * detail: When detail=true, the content of the custom page as HTML.
    """

    def get(self, request, course_id):
        """
        GET /api/courses/{course_id}/static_tabs
        """
        course_descriptor, _course_key, _course_content = get_course(request, request.user, course_id)
        if not course_descriptor:
            return Response({}, status=status.HTTP_404_NOT_FOUND)
        response_data = OrderedDict()
        tabs = []
        for tab in course_descriptor.tabs:
            if tab.type == 'static_tab':
                tab_data = OrderedDict()
                tab_data['id'] = tab.url_slug
                tab_data['name'] = tab.name
                if request.GET.get('detail') and request.GET.get('detail') in ['True', 'true']:
                    tab_data['content'] = get_static_tab_contents(
                        request,
                        course_descriptor,
                        tab,
                        wrap_xmodule_display=False
                    )
                tabs.append(tab_data)
        response_data['tabs'] = tabs
        return Response(response_data)


class CoursesStaticTabsDetail(SecureAPIView):
    """
    **Use Case**

        CoursesStaticTabsDetail returns a collection of custom pages in the
        course, including the page content.

    **Example Requests**

          GET /api/courses/{course_id}/static_tabs/{tab_id}

    **Response Values**

        * tabs: The collection of custom pages in the course. Each object in the
          collection conains the following keys:

          * id: The ID of the custom page.

          * name: The Display Name of the custom page.

          * detail: The content of the custom page as HTML.
    """

    def get(self, request, course_id, tab_id):
        """
        GET /api/courses/{course_id}/static_tabs/{tab_id}
        """
        course_descriptor, _course_key, _course_content = get_course(request, request.user, course_id)
        if not course_descriptor:
            return Response({}, status=status.HTTP_404_NOT_FOUND)
        response_data = OrderedDict()
        for tab in course_descriptor.tabs:
            if tab.type == 'static_tab' and tab.url_slug == tab_id:
                response_data['id'] = tab.url_slug
                response_data['name'] = tab.name
                response_data['content'] = get_static_tab_contents(
                    request,
                    course_descriptor,
                    tab,
                    wrap_xmodule_display=False
                )
        if not response_data:
            return Response({}, status=status.HTTP_404_NOT_FOUND)
        return Response(response_data, status=status.HTTP_200_OK)
