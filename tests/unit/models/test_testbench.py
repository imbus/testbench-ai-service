import unittest

from testbench_ai_service.models.testbench import (
    ActivityStatus,
    ExecStatus,
    OptionalUser,
    Priority,
    ProjectMember,
    ProjectRole,
    SpecificationDetailsForUpdate,
    SpecStatus,
    VerdictStatus,
)


class TestPriorityEnum(unittest.TestCase):
    def test_all_expected_members_exist(self):
        for expected in ("Undefined", "Low", "Middle", "High"):
            self.assertIn(expected, [p.value for p in Priority])


class TestSpecStatusEnum(unittest.TestCase):
    def test_all_expected_members_exist(self):
        for expected in ("NotPlanned", "Planned", "InProgress", "InReview", "Released"):
            self.assertIn(expected, [s.value for s in SpecStatus])


class TestActivityStatusEnum(unittest.TestCase):
    def test_assigned_and_canceled_exist(self):
        self.assertIn("Assigned", [s.value for s in ActivityStatus])
        self.assertIn("Canceled", [s.value for s in ActivityStatus])


class TestExecStatusEnum(unittest.TestCase):
    def test_blocked_and_not_blocked(self):
        self.assertIn("Blocked", [s.value for s in ExecStatus])
        self.assertIn("NotBlocked", [s.value for s in ExecStatus])


class TestVerdictStatusEnum(unittest.TestCase):
    def test_pass_fail_undefined_exist(self):
        values = [s.value for s in VerdictStatus]
        for expected in ("Pass", "Fail", "Undefined"):
            self.assertIn(expected, values)


class TestOptionalUser(unittest.TestCase):
    def test_defaults_to_none(self):
        user = OptionalUser()
        self.assertIsNone(user.optional)

    def test_accepts_string_value(self):
        user = OptionalUser(optional="user42")
        self.assertEqual(user.optional, "user42")


class TestSpecificationDetailsForUpdate(unittest.TestCase):
    def test_all_fields_are_optional(self):
        """Model should be constructible with no arguments."""
        spec = SpecificationDetailsForUpdate()
        self.assertIsNone(spec.responsible)
        self.assertIsNone(spec.reviewer)
        self.assertIsNone(spec.locker)

    def test_reviewer_can_be_set(self):
        spec = SpecificationDetailsForUpdate(reviewer=OptionalUser(optional="alice"))
        self.assertEqual(spec.reviewer.optional, "alice")


class TestProjectMember(unittest.TestCase):
    def test_valid_member(self):
        member = ProjectMember(
            userKey="u1",
            userLogin="alice",
            userName="Alice",
            projectKey="pk",
            projectName="My Project",
            roles=[ProjectRole.TestDesigner],
        )
        self.assertIn(ProjectRole.TestDesigner, member.roles)

    def test_empty_roles_allowed(self):
        member = ProjectMember(
            userKey="u2",
            userLogin="bob",
            userName="Bob",
            projectKey="pk2",
            projectName="P2",
            roles=[],
        )
        self.assertEqual(member.roles, [])


if __name__ == "__main__":
    unittest.main()
