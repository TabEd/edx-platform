"""
Helper methods for milestones api calls.
"""

from opaque_keys.edx.keys import CourseKey
from milestones.api import (
    get_course_milestones,
    add_milestone,
    add_course_milestone,
    remove_course_milestone,
)


def get_prerequisite_course_key(course_key):
    """
    Retrieves pre_requisite_course_key for a course from milestones app
    """
    pre_requisite_course_key = None
    course_milestones = get_course_milestones(course_key=course_key, relationship="requires")
    if course_milestones:
        pre_requisite_course_key = course_milestones[0]['namespace']
    return pre_requisite_course_key


def add_prerequisite_course(course_key, prerequisite_course_key):
    """
    adds pre-requisite course milestone to a course
    """
    # add or get a milestone to be used as requirement
    requirement_milestone = add_milestone({
        'name': 'Course {} requires {}'.format(unicode(course_key), unicode(prerequisite_course_key)),
        'namespace': unicode(prerequisite_course_key),
        'description': '',
    })
    add_course_milestone(course_key, 'requires', requirement_milestone)

    # add or get a milestone to be used as fulfillment
    fulfillment_milestone = add_milestone({
        'name': 'Course {} fulfills {}'.format(unicode(prerequisite_course_key), unicode(course_key)),
        'namespace': unicode(course_key),
        'description': '',
    })
    add_course_milestone(prerequisite_course_key, 'fulfills', fulfillment_milestone)


def remove_prerequisite_course(course_key, milestone):
    """
    remove pre-requisite course milestone for a course
    """

    remove_course_milestone(
        course_key,
        milestone,
    )


def set_prerequisite_course(course_key, prerequisite_course_key_string):
    """
    add or update pre-requisite course milestone for a course
    """
    #remove any existing requirement milestones with this pre-requisite course as requirement
    course_milestones = get_course_milestones(course_key=course_key, relationship="requires")
    if course_milestones:
        for milestone in course_milestones:
            remove_prerequisite_course(course_key, milestone)

    # add milestones if pre-requisite course is selected
    if prerequisite_course_key_string:
        prerequisite_course_key = CourseKey.from_string(prerequisite_course_key_string)
        add_prerequisite_course(course_key, prerequisite_course_key)
