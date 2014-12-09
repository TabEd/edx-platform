"""
Tests of the LMS XBlock Mixin
"""
import ddt

from opaque_keys.edx.locator import CourseLocator
from xblock.validation import ValidationMessage
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.xml import XMLModuleStore
from xmodule.partitions.partitions import Group, UserPartition
from xmodule.tests import DATA_DIR


class LmsXBlockMixinTestCase(ModuleStoreTestCase):
    """
    Base class for XBlock mixin tests cases. A simple course with a single user partition is created
    in setUp for all subclasses to use.
    """

    def setUp(self):
        super(LmsXBlockMixinTestCase, self).setUp()
        self.user_partition = UserPartition(
            0,
            'first_partition',
            'First Partition',
            [
                Group(0, 'alpha'),
                Group(1, 'beta')
            ]
        )
        self.group1 = self.user_partition.groups[0]    # pylint: disable=no-member
        self.group2 = self.user_partition.groups[1]    # pylint: disable=no-member
        self.course = CourseFactory.create(user_partitions=[self.user_partition])
        self.section = ItemFactory.create(parent=self.course, category='chapter', display_name='Test Section')
        self.subsection = ItemFactory.create(parent=self.section, category='sequential', display_name='Test Subsection')
        self.vertical = ItemFactory.create(parent=self.subsection, category='vertical', display_name='Test Unit')
        self.video = ItemFactory.create(parent=self.subsection, category='video', display_name='Test Video')


class XBlockValidationTest(LmsXBlockMixinTestCase):
    """
    Unit tests for XBlock validation
    """

    def verify_validation_message(self, message, expected_message, expected_message_type):
        """
        Verify that the validation message has the expected validation message and type.
        """
        self.assertEqual(message.text, expected_message)
        self.assertEqual(message.type, expected_message_type)

    def test_validate_full_group_access(self):
        """
        Test the validation messages produced for an xblock with full group access.
        """
        validation = self.video.validate()
        self.assertEqual(len(validation.messages), 0)

    def test_validate_restricted_group_access(self):
        """
        Test the validation messages produced for an xblock with a valid group access restriction
        """
        self.video.group_access[self.user_partition.id] = [self.group1.id, self.group2.id]  # pylint: disable=no-member
        validation = self.video.validate()
        self.assertEqual(len(validation.messages), 0)

    def test_validate_invalid_user_partition(self):
        """
        Test the validation messages produced for an xblock referring to a non-existent user partition.
        """
        self.video.group_access[999] = [self.group1.id]
        validation = self.video.validate()
        self.assertEqual(len(validation.messages), 1)
        self.verify_validation_message(
            validation.messages[0],
            u"This xblock refers to a deleted or invalid content group configuration.",
            ValidationMessage.ERROR,
        )

    def test_validate_invalid_group(self):
        """
        Test the validation messages produced for an xblock referring to a non-existent group.
        """
        self.video.group_access[self.user_partition.id] = [self.group1.id, 999]    # pylint: disable=no-member
        validation = self.video.validate()
        self.assertEqual(len(validation.messages), 1)
        self.verify_validation_message(
            validation.messages[0],
            u"This xblock refers to a deleted or invalid content group.",
            ValidationMessage.ERROR,
        )


class XBlockGroupAccessTest(LmsXBlockMixinTestCase):
    """
    Unit tests for XBlock group access.
    """

    def test_is_visible_to_group(self):
        """
        Test the behavior of is_visible_to_group.
        """
        # All groups are visible for an unrestricted xblock
        self.assertTrue(self.video.is_visible_to_group(self.user_partition, self.group1))
        self.assertTrue(self.video.is_visible_to_group(self.user_partition, self.group2))

        # Verify that all groups are visible if the set of group ids is empty
        self.video.group_access[self.user_partition.id] = []    # pylint: disable=no-member
        self.assertTrue(self.video.is_visible_to_group(self.user_partition, self.group1))
        self.assertTrue(self.video.is_visible_to_group(self.user_partition, self.group2))

        # Verify that only specified groups are visible
        self.video.group_access[self.user_partition.id] = [self.group1.id]    # pylint: disable=no-member
        self.assertTrue(self.video.is_visible_to_group(self.user_partition, self.group1))
        self.assertFalse(self.video.is_visible_to_group(self.user_partition, self.group2))

        # Verify that having an invalid user partition does not affect group visibility of other partitions
        self.video.group_access[999] = [self.group1.id]
        self.assertTrue(self.video.is_visible_to_group(self.user_partition, self.group1))
        self.assertFalse(self.video.is_visible_to_group(self.user_partition, self.group2))

        # Verify that group access is still correct even with invalid group ids
        self.video.group_access.clear()
        self.video.group_access[self.user_partition.id] = [self.group2.id, 999]    # pylint: disable=no-member
        self.assertFalse(self.video.is_visible_to_group(self.user_partition, self.group1))
        self.assertTrue(self.video.is_visible_to_group(self.user_partition, self.group2))


@ddt.ddt
class XBlockGetParentTest(LmsXBlockMixinTestCase):
    """
    Test that XBlock.get_parent returns correct results with each modulestore
    backend.
    """

    @ddt.data(ModuleStoreEnum.Type.mongo, ModuleStoreEnum.Type.split, ModuleStoreEnum.Type.xml)
    def test_parents(self, modulestore_type):
        with self.store.default_store(modulestore_type):

            # setting up our own local course tree here, since it needs to be
            # created with the correct modulestore type.

            if modulestore_type == 'xml':
                store = XMLModuleStore(DATA_DIR, course_dirs=['toy', 'simple'])
                course_key = CourseLocator.from_string('edX/toy/2012_Fall')
                course = store.get_course(course_key)
            else:
                course_key = self.create_toy_course('edX', 'toy', '2012_Fall')
                course = self.store.get_course(course_key)

            self.assertIsNone(course.get_parent())

            def recurse(parent):
                """
                Descend the course tree and ensure the result of get_parent()
                is the expected one.
                """
                visited = []
                for child in parent.get_children():
                    self.assertEqual(parent.location, child.get_parent().location)
                    visited.append(child)
                    visited += recurse(child)
                return visited

            visited = recurse(course)
            self.assertEqual(len(visited), 28)


class RenamedTuple(tuple):  # pylint: disable=incomplete-protocol
    """
    This class is only used to allow overriding __name__ on the tuples passed
    through ddt, in order to have the generated test names make sense.
    """
    pass


def ddt_named(parent, child):
    """
    Helper to get more readable dynamically-generated test names from ddt.
    """
    args = RenamedTuple([parent, child])
    setattr(args, '__name__', 'parent_{}_child_{}'.format(parent, child))
    return args


@ddt.ddt
class XBlockMergedGroupAccessTest(LmsXBlockMixinTestCase):
    """
    Test that XBlock.merged_group_access is computed correctly according to
    our access control rules.
    """

    PARTITION_1 = 1
    PARTITION_1_GROUP_1 = 11
    PARTITION_1_GROUP_2 = 12

    PARTITION_2 = 2
    PARTITION_2_GROUP_1 = 21
    PARTITION_2_GROUP_2 = 22

    PARENT_CHILD_PAIRS = (
        ddt_named('section', 'subsection'),
        ddt_named('section', 'vertical'),
        ddt_named('section', 'video'),
        ddt_named('subsection', 'vertical'),
        ddt_named('subsection', 'video'),
    )

    def set_group_access(self, block, access_dict):
        """
        DRY helper.
        """
        block.group_access = access_dict
        block.runtime.modulestore.update_item(block, 1)

    @ddt.data(*PARENT_CHILD_PAIRS)
    @ddt.unpack
    def test_intersecting_groups(self, parent, child):
        """
        When merging group_access on a block, the resulting group IDs for each
        partition is the intersection of the group IDs defined for that
        partition across all ancestor blocks (including this one).
        """
        parent_block = getattr(self, parent)
        child_block = getattr(self, child)

        self.set_group_access(parent_block, {self.PARTITION_1: [self.PARTITION_1_GROUP_1, self.PARTITION_1_GROUP_2]})
        self.set_group_access(child_block, {self.PARTITION_1: [self.PARTITION_1_GROUP_2]})

        self.assertEqual(
            parent_block.merged_group_access,
            {self.PARTITION_1: [self.PARTITION_1_GROUP_1, self.PARTITION_1_GROUP_2]},
        )
        self.assertEqual(
            child_block.merged_group_access,
            {self.PARTITION_1: [self.PARTITION_1_GROUP_2]},
        )

    @ddt.data(*PARENT_CHILD_PAIRS)
    @ddt.unpack
    def test_disjoint_groups(self, parent, child):
        """
        When merging group_access on a block, if the intersection of group IDs
        for a partition is empty, the merged value for that partition is False.
        """
        parent_block = getattr(self, parent)
        child_block = getattr(self, child)

        self.set_group_access(parent_block, {self.PARTITION_1: [self.PARTITION_1_GROUP_1]})
        self.set_group_access(child_block, {self.PARTITION_1: [self.PARTITION_1_GROUP_2]})

        self.assertEqual(
            parent_block.merged_group_access,
            {self.PARTITION_1: [self.PARTITION_1_GROUP_1]},
        )
        self.assertEqual(
            child_block.merged_group_access,
            {self.PARTITION_1: False},
        )

    @ddt.data(*PARENT_CHILD_PAIRS)
    @ddt.unpack
    def test_union_partitions(self, parent, child):
        """
        When merging group_access on a block, the result's keys (partitions)
        are the union of all partitions specified across all ancestor blocks
        (including this one).
        """
        parent_block = getattr(self, parent)
        child_block = getattr(self, child)

        self.set_group_access(parent_block, {self.PARTITION_1: [self.PARTITION_1_GROUP_1]})
        self.set_group_access(child_block, {self.PARTITION_2: [self.PARTITION_1_GROUP_2]})

        self.assertEqual(
            parent_block.merged_group_access,
            {self.PARTITION_1: [self.PARTITION_1_GROUP_1]},
        )
        self.assertEqual(
            child_block.merged_group_access,
            {self.PARTITION_1: [self.PARTITION_1_GROUP_1], self.PARTITION_2: [self.PARTITION_1_GROUP_2]},
        )
