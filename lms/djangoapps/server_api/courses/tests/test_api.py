"""
Run these tests @ Devstack:
    paver test_system -s lms --fasttest --verbose --test_id=lms/djangoapps/server_api
"""
from datetime import datetime
import json
import uuid
from urllib import urlencode

from django.core.urlresolvers import reverse
import mock
from django.core.cache import cache
from django.test import TestCase, Client
from django.test.utils import override_settings
from capa.tests.response_xml_factory import StringResponseXMLFactory
from xmodule.modulestore.tests.django_utils import TEST_DATA_MOCK_MODULESTORE
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory

from courseware import module_render
from courseware.tests.factories import StudentModuleFactory
from courseware.model_data import FieldDataCache
from django_comment_common.models import Role, FORUM_ROLE_MODERATOR
from student.tests.factories import UserFactory, CourseEnrollmentFactory
from server_api.courses.tests.fixtures import TEST_COURSE_OVERVIEW_CONTENT, TEST_COURSE_UPDATES_CONTENT, \
    TEST_COURSE_UPDATES_CONTENT_LEGACY, TEST_STATIC_TAB1_CONTENT, TEST_STATIC_TAB2_CONTENT


TEST_API_KEY = str(uuid.uuid4())
USER_COUNT = 6
SAMPLE_GRADE_DATA_COUNT = 4

HEADERS = {
    'Content-Type': 'application/json',
    'X-Edx-Api-Key': str(TEST_API_KEY),
}


class SecureClient(Client):
    """ Django test client using a "secure" connection. """

    def __init__(self, *args, **kwargs):
        kwargs = kwargs.copy()
        kwargs.update({'SERVER_PORT': 443, 'wsgi.url_scheme': 'https'})
        super(SecureClient, self).__init__(*args, **kwargs)


@override_settings(MODULESTORE=TEST_DATA_MOCK_MODULESTORE)
@override_settings(EDX_API_KEY=TEST_API_KEY)
@mock.patch.dict("django.conf.settings.FEATURES", {'ENFORCE_PASSWORD_POLICY': False,
                                                   'ADVANCED_SECURITY': False,
                                                   'PREVENT_CONCURRENT_LOGINS': False})
class CoursesApiTests(TestCase):
    """ Test suite for Courses API views """

    def get_module_for_user(self, user, course, problem):
        """Helper function to get useful module at self.location in self.course_id for user"""
        mock_request = mock.MagicMock()
        mock_request.user = user
        field_data_cache = FieldDataCache.cache_for_descriptor_descendents(
            course.id, user, course, depth=2)
        module = module_render.get_module(  # pylint: disable=protected-access
                                            user,
                                            mock_request,
                                            problem.location,
                                            field_data_cache,
                                            course.id
        )
        return module

    def setUp(self):  # pylint: disable=R0915
        self.test_server_prefix = 'https://testserver'
        self.base_courses_uri = reverse('server_api:courses:list')

        self.course = CourseFactory.create(
            start=datetime(2014, 6, 16, 14, 30),
            end=datetime(2015, 1, 16)
        )
        self.test_data = '<html>{}</html>'.format(str(uuid.uuid4()))

        self.chapter = ItemFactory.create(
            category="chapter",
            parent_location=self.course.location,
            data=self.test_data,
            due=datetime(2014, 5, 16, 14, 30),
            display_name="Overview"
        )

        self.course_project = ItemFactory.create(
            category="chapter",
            parent_location=self.course.location,
            data=self.test_data,
            display_name="Group Project"
        )

        self.course_project2 = ItemFactory.create(
            category="chapter",
            parent_location=self.course.location,
            data=self.test_data,
            display_name="Group Project2"
        )

        self.course_content = ItemFactory.create(
            category="videosequence",
            parent_location=self.chapter.location,
            data=self.test_data,
            display_name="Video_Sequence"
        )

        self.content_child = ItemFactory.create(
            category="video",
            parent_location=self.course_content.location,
            data=self.test_data,
            display_name="Video_Resources"
        )

        self.overview = ItemFactory.create(
            category="about",
            parent_location=self.course.location,
            data=TEST_COURSE_OVERVIEW_CONTENT,
            display_name="overview"
        )

        self.updates = ItemFactory.create(
            category="course_info",
            parent_location=self.course.location,
            data=TEST_COURSE_UPDATES_CONTENT,
            display_name="updates"
        )

        self.static_tab1 = ItemFactory.create(
            category="static_tab",
            parent_location=self.course.location,
            data=TEST_STATIC_TAB1_CONTENT,
            display_name="syllabus"
        )

        self.static_tab2 = ItemFactory.create(
            category="static_tab",
            parent_location=self.course.location,
            data=TEST_STATIC_TAB2_CONTENT,
            display_name="readings"
        )

        self.sub_section = ItemFactory.create(
            parent_location=self.chapter.location,
            category="sequential",
            display_name=u"test subsection",
        )

        self.unit = ItemFactory.create(
            parent_location=self.sub_section.location,
            category="vertical",
            metadata={'graded': True, 'format': 'Homework'},
            display_name=u"test unit",
        )

        self.dash_unit = ItemFactory.create(
            parent_location=self.sub_section.location,
            category="vertical-with-dash",
            metadata={'graded': True, 'format': 'Homework'},
            display_name=u"test unit 2",
        )

        self.empty_course = CourseFactory.create(
            start=datetime(2014, 6, 16, 14, 30),
            end=datetime(2015, 1, 16),
            org="MTD"
        )

        self.users = [UserFactory.create(username="testuser" + str(__), profile='test') for __ in xrange(USER_COUNT)]

        for user in self.users:
            CourseEnrollmentFactory.create(user=user, course_id=self.course.id)
            user_profile = user.profile
            user_profile.avatar_url = 'http://example.com/{}.png'.format(user.id)
            user_profile.title = 'Software Engineer {}'.format(user.id)
            user_profile.city = 'Cambridge'
            user_profile.save()

        for i in xrange(SAMPLE_GRADE_DATA_COUNT - 1):
            section = 'Midterm Exam'
            if i % 2 is 0:
                section = "Final Exam"
            self.item = ItemFactory.create(
                parent_location=self.chapter.location,
                category='problem',
                data=StringResponseXMLFactory().build_xml(answer='bar'),
                display_name='Problem {}'.format(i),
                metadata={'rerandomize': 'always', 'graded': True, 'format': section}
            )

            for j, user in enumerate(self.users):
                points_scored = (j + 1) * 20
                points_possible = 100
                module = self.get_module_for_user(user, self.course, self.item)
                grade_dict = {'value': points_scored, 'max_value': points_possible, 'user_id': user.id}
                module.system.publish(module, 'grade', grade_dict)

                StudentModuleFactory.create(
                    course_id=self.course.id,
                    module_type='sequential',
                    module_state_key=self.item.location,
                )

        self.test_course_id = unicode(self.course.id)
        self.test_bogus_course_id = 'foo/bar/baz'
        self.test_course_name = self.course.display_name
        self.test_course_number = self.course.number
        self.test_course_org = self.course.org
        self.test_chapter_id = unicode(self.chapter.scope_ids.usage_id)
        self.test_course_content_id = unicode(self.course_content.scope_ids.usage_id)
        self.test_bogus_content_id = "j5y://foo/bar/baz"
        self.test_content_child_id = unicode(self.content_child.scope_ids.usage_id)

        self.client = SecureClient()
        cache.clear()

        Role.objects.get_or_create(
            name=FORUM_ROLE_MODERATOR,
            course_id=self.course.id)

    def do_get(self, uri):
        """Submit an HTTP GET request"""
        response = self.client.get(uri, headers=HEADERS, follow=True)
        return response

    def do_post(self, uri, data):
        """Submit an HTTP POST request"""
        json_data = json.dumps(data)
        response = self.client.post(uri, headers=HEADERS, content_type='application/json', data=json_data)
        return response

    def do_delete(self, uri):
        """Submit an HTTP DELETE request"""
        response = self.client.delete(uri, headers=HEADERS)
        return response

    def _find_item_by_class(self, items, class_name):
        """Helper method to match a single matching item"""
        for item in items:
            if item['class'] == class_name:
                return item
        return None

    def test_courses_list_get(self):
        test_uri = reverse('server_api:courses:list') + '?page_size=150'
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data['results']), 0)
        self.assertIsNotNone(response.data['count'])
        self.assertIsNotNone(response.data['num_pages'])
        matched_course = False
        for course in response.data['results']:
            if matched_course is False and course['id'] == self.test_course_id:
                self.assertEqual(course['name'], self.test_course_name)
                self.assertEqual(course['number'], self.test_course_number)
                self.assertEqual(course['org'], self.test_course_org)
                confirm_uri = self.test_server_prefix + reverse('server_api:courses:detail',
                                                                kwargs={'course_id': course['id']})
                self.assertEqual(course['uri'], confirm_uri)
                matched_course = True
        self.assertTrue(matched_course)

    def test_courses_list_get_with_filter(self):
        test_uri = reverse('server_api:courses:list')
        courses = [self.test_course_id, unicode(self.empty_course.id)]
        params = {'course_id': ','.join(courses).encode('utf-8')}
        response = self.do_get('{}?{}'.format(test_uri, urlencode(params)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 2)
        self.assertIsNotNone(response.data['count'])
        self.assertIsNotNone(response.data['num_pages'])
        courses_in_result = []
        for course in response.data['results']:
            courses_in_result.append(course['id'])
            if course['id'] == self.test_course_id:
                self.assertEqual(course['name'], self.test_course_name)
                self.assertEqual(course['number'], self.test_course_number)
                self.assertEqual(course['org'], self.test_course_org)
                confirm_uri = self.test_server_prefix + reverse('server_api:courses:detail',
                                                                kwargs={'course_id': course['id']})
                self.assertEqual(course['uri'], confirm_uri)
                self.assertIsNotNone(course['course_image_url'])
        self.assertItemsEqual(courses, courses_in_result)

    def test_course_detail_without_date_values(self):
        # Create course without date values
        course = CourseFactory.create()  # pylint: disable=C0103
        test_uri = reverse('server_api:courses:detail', kwargs={'course_id': unicode(course.id)})
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['start'], course.start)
        self.assertEqual(response.data['end'], course.end)

    def test_courses_detail_get(self):
        test_uri = reverse('server_api:courses:detail', kwargs={'course_id': self.test_course_id})
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        self.assertEqual(response.data['id'], self.test_course_id)
        self.assertEqual(response.data['name'], self.test_course_name)
        time_format = '%Y-%m-%d %H:%M:%S'
        self.assertEqual(datetime.strftime(response.data['start'], time_format),
                         datetime.strftime(self.course.start, time_format))
        self.assertEqual(datetime.strftime(response.data['end'], time_format),
                         datetime.strftime(self.course.end, time_format))
        self.assertEqual(response.data['number'], self.test_course_number)
        self.assertEqual(response.data['org'], self.test_course_org)
        confirm_uri = self.test_server_prefix + test_uri
        self.assertEqual(response.data['uri'], confirm_uri)

    def test_courses_detail_get_with_child_content(self):
        test_uri = reverse('server_api:courses:detail', kwargs={'course_id': self.test_course_id})
        response = self.do_get('{}?depth=100'.format(test_uri))
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        self.assertEqual(response.data['id'], self.test_course_id)
        self.assertEqual(response.data['name'], self.test_course_name)
        self.assertEqual(response.data['number'], self.test_course_number)
        self.assertEqual(response.data['org'], self.test_course_org)
        confirm_uri = self.test_server_prefix + test_uri
        self.assertEqual(response.data['uri'], confirm_uri)
        self.assertGreater(len(response.data['content']), 0)
        for resource in response.data['resources']:
            print resource['uri']
            response = self.do_get(resource['uri'])
            self.assertEqual(response.status_code, 200)

    def test_courses_detail_get_notfound(self):
        test_uri = self.base_courses_uri + '/' + self.test_bogus_course_id
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 404)

    def test_courses_tree_get(self):
        # query the course tree to quickly get navigation information
        test_uri = reverse('server_api:courses:detail', kwargs={'course_id': self.test_course_id}) + '?depth=2'
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        self.assertEqual(response.data['category'], 'course')
        self.assertEqual(response.data['name'], self.course.display_name)
        self.assertEqual(len(response.data['content']), 3)

        chapter = response.data['content'][0]
        self.assertEqual(chapter['category'], 'chapter')
        self.assertEqual(chapter['name'], 'Overview')
        self.assertEqual(len(chapter['children']), 5)

        sequence = chapter['children'][0]
        self.assertEqual(sequence['category'], 'videosequence')
        self.assertEqual(sequence['name'], 'Video_Sequence')
        self.assertNotIn('children', sequence)

    def test_courses_tree_get_root(self):
        # query the course tree to quickly get navigation information
        test_uri = reverse('server_api:courses:detail', kwargs={'course_id': self.test_course_id}) + '?depth=0'
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        self.assertEqual(response.data['category'], 'course')
        self.assertEqual(response.data['name'], self.course.display_name)
        self.assertNotIn('content', response.data)

    def test_chapter_list_get(self):
        test_uri = reverse('server_api:courses:content_list',
                           kwargs={'course_id': self.test_course_id}) + '?type=chapter'
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        matched_chapter = False
        for chapter in response.data:
            if matched_chapter is False and chapter['id'] == self.test_chapter_id:
                self.assertIsNotNone(chapter['uri'])
                self.assertGreater(len(chapter['uri']), 0)
                confirm_uri = self.test_server_prefix + reverse('server_api:courses:content_detail',
                                                                kwargs={'course_id': self.test_course_id,
                                                                        'content_id': chapter['id']})
                self.assertEqual(chapter['uri'], confirm_uri)
                matched_chapter = True
        self.assertTrue(matched_chapter)

    def test_chapter_detail_get(self):
        test_uri = reverse('server_api:courses:content_detail',
                           kwargs={'course_id': self.test_course_id, 'content_id': self.test_chapter_id})
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data['id']), 0)
        self.assertEqual(response.data['id'], self.test_chapter_id)
        confirm_uri = self.test_server_prefix + test_uri
        self.assertEqual(response.data['uri'], confirm_uri)
        self.assertGreater(len(response.data['children']), 0)

    def test_course_content_list_get(self):
        test_uri = reverse('server_api:courses:content_children_list',
                           kwargs={'course_id': self.test_course_id, 'content_id': self.test_course_content_id})
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        matched_child = False
        for child in response.data:
            if matched_child is False and child['id'] == self.test_content_child_id:
                self.assertIsNotNone(child['uri'])
                self.assertGreater(len(child['uri']), 0)
                confirm_uri = self.test_server_prefix + reverse('server_api:courses:content_detail',
                                                                kwargs={'course_id': self.test_course_id,
                                                                        'content_id': child['id']})
                self.assertEqual(child['uri'], confirm_uri)
                matched_child = True
        self.assertTrue(matched_child)

    def test_course_content_list_get_invalid_course(self):
        test_uri = reverse('server_api:courses:content_children_list',
                           kwargs={'course_id': self.test_bogus_course_id,
                                   'content_id': unicode(self.course_project.scope_ids.usage_id)})
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 404)

    def test_course_content_list_get_invalid_content(self):
        test_uri = reverse('server_api:courses:content_children_list',
                           kwargs={'course_id': self.test_course_id, 'content_id': self.test_bogus_content_id})
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 404)

    def test_course_content_detail_get(self):
        test_uri = reverse('server_api:courses:content_detail',
                           kwargs={'course_id': self.test_course_id, 'content_id': self.test_course_content_id})
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        self.assertEqual(response.data['id'], self.test_course_content_id)
        confirm_uri = self.test_server_prefix + test_uri
        self.assertEqual(response.data['uri'], confirm_uri)
        self.assertGreater(len(response.data['children']), 0)

    def test_course_content_detail_get_with_extra_fields(self):
        test_uri = reverse('server_api:courses:content_detail',
                           kwargs={'course_id': self.test_course_id, 'content_id': self.test_course_content_id})
        response = self.do_get('{}?include_fields=course_edit_method'.format(test_uri))
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        self.assertIsNotNone(response.data['course_edit_method'])

    def test_course_content_detail_get_dashed_id(self):
        test_content_id = unicode(self.dash_unit.scope_ids.usage_id)
        test_uri = reverse('server_api:courses:content_detail',
                           kwargs={'course_id': self.test_course_id, 'content_id': test_content_id})
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        self.assertEqual(response.data['id'], test_content_id)
        confirm_uri = self.test_server_prefix + test_uri
        self.assertEqual(response.data['uri'], confirm_uri)

    def test_course_content_detail_get_course(self):
        test_uri = reverse('server_api:courses:content_detail',
                           kwargs={'course_id': self.test_course_id, 'content_id': self.test_course_id})
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        self.assertEqual(response.data['id'], self.test_course_id)
        confirm_uri = self.test_server_prefix + reverse('server_api:courses:detail',
                                                        kwargs={'course_id': self.test_course_id})
        self.assertEqual(response.data['uri'], confirm_uri)
        self.assertGreater(len(response.data['content']), 0)

    def test_course_content_detail_get_not_found(self):
        test_uri = reverse('server_api:courses:content_list', kwargs={'course_id': self.test_bogus_course_id})
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 404)

    def test_course_content_list_get_filtered_children_for_child(self):
        test_uri = reverse('server_api:courses:content_children_list',
                           kwargs={'course_id': self.test_course_id,
                                   'content_id': self.test_course_content_id}) + '?type=video'

        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        matched_child = False
        for child in response.data:
            if matched_child is False and child['id'] == self.test_content_child_id:
                confirm_uri = self.test_server_prefix + reverse('server_api:courses:content_detail',
                                                                kwargs={'course_id': self.test_course_id,
                                                                        'content_id': child['id']})
                self.assertEqual(child['uri'], confirm_uri)
                matched_child = True
        self.assertTrue(matched_child)

    def test_course_content_list_get_not_found(self):
        test_uri = reverse('server_api:courses:content_children_list', kwargs={'course_id': self.test_course_id,
                                                                               'content_id': self.test_bogus_content_id}) + '?type=video'
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 404)

    def test_courses_overview_get_unparsed(self):
        test_uri = reverse('server_api:courses:overview', kwargs={'course_id': self.test_course_id})

        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        self.assertEqual(response.data['overview_html'], self.overview.data)
        self.assertIn(self.course.course_image, response.data['course_image_url'])

    def test_courses_overview_get_invalid_course(self):
        # try a bogus course_id to test failure case
        test_uri = reverse('server_api:courses:overview', kwargs={'course_id': self.test_bogus_course_id})
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 404)

    def test_courses_overview_get_invalid_content(self):
        # try a bogus course_id to test failure case
        test_course = CourseFactory.create()
        test_uri = reverse('server_api:courses:overview', kwargs={'course_id': unicode(test_course.id)})
        ItemFactory.create(
            category="about",
            parent_location=test_course.location,
            data='',
            display_name="overview"
        )
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 404)

    def test_courses_updates_get(self):
        # first try raw without any parsing
        test_uri = reverse('server_api:courses:updates', kwargs={'course_id': self.test_course_id})
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        self.assertEqual(response.data['content'], self.updates.data)

        # then try parsed
        test_uri += '?parse=True'
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)

        postings = response.data['postings']
        self.assertEqual(len(postings), 4)
        self.assertEqual(postings[0]['date'], 'April 18, 2014')
        self.assertEqual(postings[0]['content'], 'This does not have a paragraph tag around it')
        self.assertEqual(postings[1]['date'], 'April 17, 2014')
        self.assertEqual(postings[1]['content'],
                         'Some text before paragraph tag<p>This is inside paragraph tag</p>Some text after tag')
        self.assertEqual(postings[2]['date'], 'April 16, 2014')
        self.assertEqual(postings[2]['content'],
                         'Some text before paragraph tag<p>This is inside paragraph tag</p>Some text after tag<p>one more</p>')
        self.assertEqual(postings[3]['date'], 'April 15, 2014')
        self.assertEqual(postings[3]['content'], '<p>A perfectly</p><p>formatted piece</p><p>of HTML</p>')

    def test_courses_updates_get_invalid_course(self):
        # try a bogus course_id to test failure case
        test_uri = reverse('server_api:courses:updates', kwargs={'course_id': self.test_bogus_course_id})
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 404)

    def test_courses_updates_get_invalid_content(self):
        # try a bogus course_id to test failure case
        test_course = CourseFactory.create()
        ItemFactory.create(
            category="course_info",
            parent_location=test_course.location,
            data='',
            display_name="updates"
        )
        path = reverse('server_api:courses:updates', kwargs={'course_id': unicode(test_course.id)})
        response = self.do_get(path)
        self.assertEqual(response.status_code, 404)

    def test_courses_updates_legacy(self):
        # try a bogus course_id to test failure case
        test_course = CourseFactory.create()
        ItemFactory.create(
            category="course_info",
            parent_location=test_course.location,
            data=TEST_COURSE_UPDATES_CONTENT_LEGACY,
            display_name="updates"
        )
        path = reverse('server_api:courses:updates', kwargs={'course_id': unicode(test_course.id)})
        response = self.do_get(path)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        self.assertEqual(response.data['content'], TEST_COURSE_UPDATES_CONTENT_LEGACY)

        # then try parsed
        path += '?parse=True'
        response = self.do_get(path)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)

        postings = response.data['postings']
        self.assertEqual(len(postings), 4)
        self.assertEqual(postings[0]['date'], 'April 18, 2014')
        self.assertEqual(postings[0]['content'], 'This is some legacy content')
        self.assertEqual(postings[1]['date'], 'April 17, 2014')
        self.assertEqual(postings[1]['content'],
                         'Some text before paragraph tag<p>This is inside paragraph tag</p>Some text after tag')
        self.assertEqual(postings[2]['date'], 'April 16, 2014')
        self.assertEqual(postings[2]['content'],
                         'Some text before paragraph tag<p>This is inside paragraph tag</p>Some text after tag<p>one more</p>')
        self.assertEqual(postings[3]['date'], 'April 15, 2014')
        self.assertEqual(postings[3]['content'], '<p>A perfectly</p><p>formatted piece</p><p>of HTML</p>')

    def test_static_tab_list_get(self):
        path = reverse('server_api:courses:static_tabs_list', kwargs={'course_id': self.test_course_id})
        response = self.do_get(path)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)

        tabs = response.data['tabs']
        self.assertEqual(len(tabs), 2)
        self.assertEqual(tabs[0]['name'], u'syllabus')
        self.assertEqual(tabs[0]['id'], u'syllabus')
        self.assertEqual(tabs[1]['name'], u'readings')
        self.assertEqual(tabs[1]['id'], u'readings')

        # now try when we get the details on the tabs
        path += '?detail=true'
        response = self.do_get(path)

        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)

        tabs = response.data['tabs']
        self.assertEqual(tabs[0]['name'], u'syllabus')
        self.assertEqual(tabs[0]['id'], u'syllabus')
        self.assertEqual(tabs[0]['content'], self.static_tab1.data)
        self.assertEqual(tabs[1]['name'], u'readings')
        self.assertEqual(tabs[1]['id'], u'readings')
        self.assertEqual(tabs[1]['content'], self.static_tab2.data)

    def test_static_tab_list_get_invalid_course(self):
        # Try a bogus course_id to test failure case
        path = reverse('server_api:courses:static_tabs_list', kwargs={'course_id': self.test_bogus_course_id})
        response = self.do_get(path)
        self.assertEqual(response.status_code, 404)

    def test_static_tab_detail_get(self):
        path = reverse('server_api:courses:static_tabs_detail',
                       kwargs={'course_id': self.test_course_id, 'tab_id': 'syllabus'})
        response = self.do_get(path)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        tab = response.data
        self.assertEqual(tab['name'], u'syllabus')
        self.assertEqual(tab['id'], u'syllabus')
        self.assertEqual(tab['content'], self.static_tab1.data)

        path = reverse('server_api:courses:static_tabs_detail',
                       kwargs={'course_id': self.test_course_id, 'tab_id': 'readings'})
        response = self.do_get(path)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        tab = response.data
        self.assertEqual(tab['name'], u'readings')
        self.assertEqual(tab['id'], u'readings')
        self.assertEqual(tab['content'], self.static_tab2.data)

    def test_static_tab_detail_get_invalid_course(self):
        # try a bogus courseId
        path = reverse('server_api:courses:static_tabs_detail',
                       kwargs={'course_id': self.test_bogus_course_id, 'tab_id': 'syllabus'})
        response = self.do_get(path)
        self.assertEqual(response.status_code, 404)

    def test_static_tab_detail_get_invalid_item(self):
        # try a not found item
        path = reverse('server_api:courses:static_tabs_detail',
                       kwargs={'course_id': self.test_course_id, 'tab_id': 'bogus'})
        response = self.do_get(path)
        self.assertEqual(response.status_code, 404)
