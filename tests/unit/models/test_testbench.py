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


class TestPriorityEnum:
    def test_all_expected_members_exist(self):
        for expected in ("Undefined", "Low", "Middle", "High"):
            assert expected in [p.value for p in Priority]


class TestSpecStatusEnum:
    def test_all_expected_members_exist(self):
        for expected in ("NotPlanned", "Planned", "InProgress", "InReview", "Released"):
            assert expected in [s.value for s in SpecStatus]


class TestActivityStatusEnum:
    def test_assigned_and_canceled_exist(self):
        assert "Assigned" in [s.value for s in ActivityStatus]
        assert "Canceled" in [s.value for s in ActivityStatus]


class TestExecStatusEnum:
    def test_blocked_and_not_blocked(self):
        assert "Blocked" in [s.value for s in ExecStatus]
        assert "NotBlocked" in [s.value for s in ExecStatus]


class TestVerdictStatusEnum:
    def test_pass_fail_undefined_exist(self):
        values = [s.value for s in VerdictStatus]
        for expected in ("Pass", "Fail", "Undefined"):
            assert expected in values


class TestOptionalUser:
    def test_defaults_to_none(self):
        user = OptionalUser()
        assert user.optional is None

    def test_accepts_string_value(self):
        user = OptionalUser(optional="user42")
        assert user.optional == "user42"


class TestSpecificationDetailsForUpdate:
    def test_all_fields_are_optional(self):
        """Model should be constructible with no arguments."""
        spec = SpecificationDetailsForUpdate()
        assert spec.responsible is None
        assert spec.reviewer is None
        assert spec.locker is None

    def test_reviewer_can_be_set(self):
        spec = SpecificationDetailsForUpdate(reviewer=OptionalUser(optional="alice"))
        assert spec.reviewer.optional == "alice"


class TestProjectMember:
    def test_valid_member(self):
        member = ProjectMember(
            userKey="u1",
            userLogin="alice",
            userName="Alice",
            projectKey="pk",
            projectName="My Project",
            roles=[ProjectRole.TestDesigner],
        )
        assert ProjectRole.TestDesigner in member.roles

    def test_empty_roles_allowed(self):
        member = ProjectMember(
            userKey="u2",
            userLogin="bob",
            userName="Bob",
            projectKey="pk2",
            projectName="P2",
            roles=[],
        )
        assert member.roles == []
