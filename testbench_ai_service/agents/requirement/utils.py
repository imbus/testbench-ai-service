import asyncio
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter
from testbench_cli_reporter.testbench import Connection as TBConnection

from testbench_ai_service.agents.requirement.model import (
    Baseline,
    Requirement,
    RequirementsLoaderJob,
    RequirementUdfs,
)
from testbench_ai_service.log import logger
from testbench_ai_service.models.language import LanguageOption
from testbench_ai_service.models.testbench import (
    OptionalUser,
    RichTextInfo,
    SpecificationDetailsForUpdate,
)
from testbench_ai_service.utils.html_utils import escape_html, has_visible_text
from testbench_ai_service.utils.template_utils import render_template, resolve_template_path
from testbench_ai_service.utils.testbench import patch_test_structure_element_spec
from testbench_ai_service.utils.time_utils import current_time

#: Seconds to wait between polls of the requirements loader job.
REQUIREMENTS_JOB_POLL_INTERVAL = 1.0

#: Seconds to wait for the requirements loader job to complete before giving up.
REQUIREMENTS_JOB_TIMEOUT = 120.0


async def get_legacy_json(conn: TBConnection, url: str) -> Any:
    """GET a legacy TestBench URL without blocking the event loop.

    ``conn.legacy_session`` is a synchronous ``requests.Session``, so the call is
    handed off to a worker thread. Its ``raise_for_status`` response hook means a
    non-2xx status raises ``requests.HTTPError`` from here.

    Args:
        conn: The active TestBench connection.
        url: Fully-qualified legacy API URL.

    Returns:
        The decoded JSON body.
    """
    response = await asyncio.to_thread(conn.legacy_session.get, url)
    return response.json()


async def load_requirements(
    conn: TBConnection,
    tov_key: str,
    baseline_serial: str,
    *,
    timeout: float = REQUIREMENTS_JOB_TIMEOUT,
    poll_interval: float = REQUIREMENTS_JOB_POLL_INTERVAL,
) -> Any:
    """Load the requirements of a baseline, waiting for the loader job to finish.

    Requesting the requirements of a baseline starts an asynchronous loader job and
    returns ``{"jobID": ..., "completed": false}``. The requirements endpoint is
    polled until it reports ``completed``, then the job result is fetched from
    ``requirementsLoaderJob/{jobID}``.

    The job id from the *completed* poll is the one used to fetch the result, so a
    server that hands out a fresh job id per request still yields a consistent read.

    Args:
        conn: The active TestBench connection.
        tov_key: Key of the TOV owning the baseline.
        baseline_serial: Serial of the baseline to load requirements for.
        timeout: Seconds to wait for completion before raising.
        poll_interval: Seconds between polls.

    Returns:
        The decoded requirements payload from the loader job.

    Raises:
        RuntimeError: If the job is not triggered, or does not complete in time.
    """
    requirements_url = (
        f"{conn.server_legacy_url}tovs/{tov_key}/baselines/{baseline_serial}/requirements"
    )
    deadline = time.monotonic() + timeout
    job_id: str | None = None
    polls = 0

    while True:
        job = await get_legacy_json(conn, requirements_url)
        polls += 1

        previous_job_id = job_id
        job_id = job.get("jobID")
        if not isinstance(job_id, str):
            raise RuntimeError(
                f"Requirements loader job for baseline '{baseline_serial}' was not triggered: {job}"
            )
        if previous_job_id is not None and previous_job_id != job_id:
            logger.debug(
                "Requirements endpoint returned a new job id ('%s' -> '%s'); "
                "each poll appears to start a new loader job",
                previous_job_id,
                job_id,
            )

        if job.get("completed"):
            logger.debug("Requirements loader job '%s' completed after %d poll(s)", job_id, polls)
            break

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(
                f"Requirements loader job '{job_id}' for baseline '{baseline_serial}' "
                f"did not complete within {timeout:g}s ({polls} poll(s))."
            )
        await asyncio.sleep(min(poll_interval, remaining))

    return await get_legacy_json(conn, f"{conn.server_legacy_url}requirementsLoaderJob/{job_id}")


def parse_loader_job(payload: Any) -> Baseline:
    """Validate a requirements loader job payload and unwrap its baseline.

    The job result is an ``Either``: ``completion.result.Right`` holds the baseline
    on success, ``completion.result.Left`` an error description.

    Args:
        payload: The decoded ``requirementsLoaderJob/{jobId}`` body.

    Returns:
        The baseline with its requirement tree.

    Raises:
        RuntimeError: If the job has not completed, failed, or returned neither branch.
    """
    job = RequirementsLoaderJob.model_validate(payload)

    if job.completion is None:
        raise RuntimeError(f"Requirements loader job '{job.id}' has not completed yet.")

    result = job.completion.result
    if result.left is not None:
        error = result.left
        raise RuntimeError(
            f"Requirements loader job '{job.id}' failed: {error.message or '--'} "
            f"(details: {error.details or '--'}, cause: {error.cause or '--'})"
        )
    if result.right is None:
        raise RuntimeError(
            f"Requirements loader job '{job.id}' returned neither a result nor an error."
        )

    baseline = result.right
    if not baseline.areRequirementsLoaded:
        logger.warning(
            "Baseline '%s' reports requirements as not loaded (loadingError: %s)",
            baseline.key.serial,
            baseline.loadingError,
        )
    return baseline


def iter_requirements(requirements: Iterable[Requirement]) -> Iterator[Requirement]:
    """Walk a requirement tree depth-first, yielding every node.

    Args:
        requirements: The root requirements to walk.

    Yields:
        Each requirement in the tree, parents before their children.
    """
    for requirement in requirements:
        yield requirement
        yield from iter_requirements(requirement.children)


def attach_udfs(
    requirements: Iterable[Requirement],
    udfs: Iterable[RequirementUdfs],
) -> int:
    """Attach each UDF entry to its corresponding requirement, in place.

    UDF entries are keyed by ``Requirement.requirementKey``, not by
    ``Requirement.key`` -- the latter is the baseline-scoped node key and shares no
    values with the UDF keys.

    Requirements with no matching entry keep their empty ``udfs`` list. Entries
    matching no requirement in the tree are logged and skipped.

    Args:
        requirements: The root requirements whose tree should be populated.
        udfs: The entries from ``baselines/{serial}/udfs``.

    Returns:
        The number of requirements that received at least one UDF.
    """
    by_requirement_key = {entry.key.serial: entry.value for entry in udfs}
    matched: set[str] = set()
    populated = 0

    for requirement in iter_requirements(requirements):
        serial = requirement.requirementKey.serial
        entry = by_requirement_key.get(serial)
        if entry is None:
            continue
        matched.add(serial)
        requirement.udfs = list(entry)
        if entry:
            populated += 1

    unmatched = set(by_requirement_key) - matched
    if unmatched:
        logger.warning(
            "%d UDF entr(y/ies) matched no requirement in the tree: %s",
            len(unmatched),
            sorted(unmatched),
        )
    return populated


#: The baseline type the agent generates test ideas from.
CURRENT_BASELINE_TYPE = "CURRENT"


async def load_current_baseline(
    conn: TBConnection,
    tov_key: str,
    **load_kwargs: Any,
) -> Baseline:
    """Load the TOV's current baseline, with UDFs attached to its requirements.

    Exactly one baseline is loaded. Loading every baseline would be far more
    expensive than it looks: each one starts a polled loader job with a
    :data:`REQUIREMENTS_JOB_TIMEOUT` ceiling, so a TOV with several baselines of
    thousands of requirements costs minutes per trigger for trees that are then
    discarded.

    A missing ``CURRENT`` entry raises rather than falling back to another baseline.
    The same requirement appears in several baselines at different versions, so an
    arbitrary choice would silently generate test ideas from a stale requirement --
    a wrong answer, which is worse here than no answer.

    Args:
        conn: The active TestBench connection.
        tov_key: Key of the TOV whose baselines are listed.
        **load_kwargs: Forwarded to :func:`load_requirements`, e.g. ``poll_interval``.

    Returns:
        The current baseline with its requirement tree and UDFs.

    Raises:
        RuntimeError: If no listed baseline is of type ``CURRENT``.
    """
    listing = await get_legacy_json(conn, f"{conn.server_legacy_url}tovs/{tov_key}/baselines")

    entries = listing.get("baselines", [])

    serial = next(
        (entry["key"]["key"]["serial"] for entry in entries),
        None,
    )
    if serial is None:
        raise RuntimeError(
            f"No {CURRENT_BASELINE_TYPE} baseline among the {len(entries)} baseline(s) of TOV "
            f"'{tov_key}': {[entry.get('type') for entry in entries]}"
        )

    logger.debug("Loading %s baseline '%s' of TOV '%s'", CURRENT_BASELINE_TYPE, serial, tov_key)
    job_payload = await load_requirements(conn, tov_key, serial, **load_kwargs)
    print(job_payload)
    baseline = parse_loader_job(job_payload)

    udf_payload = await get_legacy_json(
        conn, f"{conn.server_legacy_url}tovs/{tov_key}/baselines/{serial}/udfs"
    )
    udfs = TypeAdapter(list[RequirementUdfs]).validate_python(udf_payload)
    populated = attach_udfs(baseline.children, udfs)

    logger.debug(
        "Loaded baseline '%s' with %d requirement(s), %d carrying UDFs",
        baseline.name,
        sum(1 for _ in iter_requirements(baseline.children)),
        populated,
    )
    return baseline


#: Agent key used to resolve this agent's write-back templates.
AGENT_KEY = "requirement"


async def patch_generation_started(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    previous_description: str,
    language: LanguageOption,
    user_key: str,
    templates_dir: Path,
):
    """Mark a theme as having test idea generation in progress, and lock it.

    Args:
        conn: The active TestBench connection.
        project_key: Key of the project owning the specification.
        spec_key: The theme specification to patch.
        previous_description: The description to preserve below the marker.
        language: Language of the rendered marker.
        user_key: The triggering user, recorded as locker and reviewer.
        templates_dir: Root of the write-back templates.
    """
    template_path = resolve_template_path(
        "started.jinja", templates_dir=templates_dir, language=language, agent_key=AGENT_KEY
    )
    description_html = render_template(
        template_path,
        {
            "current_time": current_time(),
            "previous_description": previous_description
            if has_visible_text(previous_description)
            else None,
        },
    )
    spec_update = SpecificationDetailsForUpdate(
        reviewer=OptionalUser(optional=user_key),
        locker=OptionalUser(optional=user_key),
        description=RichTextInfo(html=description_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)


async def patch_generated_test_ideas(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    test_ideas: str,
    previous_description: str,
    language: LanguageOption,
    user_key: str,
    templates_dir: Path,
):
    """Write the generated test ideas into a theme's description and unlock it.

    Args:
        conn: The active TestBench connection.
        project_key: Key of the project owning the specification.
        spec_key: The theme specification to patch.
        test_ideas: The model's output, escaped before rendering.
        previous_description: The description to preserve above the ideas.
        language: Language of the rendered wrapper.
        user_key: The triggering user, recorded as reviewer.
        templates_dir: Root of the write-back templates.
    """
    template_path = resolve_template_path(
        "template.jinja", templates_dir=templates_dir, language=language, agent_key=AGENT_KEY
    )
    description_html = render_template(
        template_path,
        {
            "current_time": current_time(),
            "description": escape_html(test_ideas),
            "previous_description": previous_description
            if has_visible_text(previous_description)
            else None,
        },
    )
    spec_update = SpecificationDetailsForUpdate(
        locker=OptionalUser(optional=None),
        reviewer=OptionalUser(optional=user_key),
        description=RichTextInfo(html=description_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)


async def patch_generation_failed(
    conn: TBConnection,
    project_key: str,
    spec_key: str,
    previous_description: str,
    language: LanguageOption,
    user_key: str,
    templates_dir: Path,
):
    """Restore a theme's previous description after a failure, and unlock it.

    Args:
        conn: The active TestBench connection.
        project_key: Key of the project owning the specification.
        spec_key: The theme specification to patch.
        previous_description: The description to restore.
        language: Language of the rendered notice.
        user_key: The triggering user, recorded as reviewer.
        templates_dir: Root of the write-back templates.
    """
    template_path = resolve_template_path(
        "failed.jinja", templates_dir=templates_dir, language=language, agent_key=AGENT_KEY
    )
    description_html = render_template(
        template_path,
        {
            "current_time": current_time(),
            "previous_description": previous_description
            if has_visible_text(previous_description)
            else None,
        },
    )
    spec_update = SpecificationDetailsForUpdate(
        reviewer=OptionalUser(optional=user_key),
        locker=OptionalUser(optional=None),
        description=RichTextInfo(html=description_html, images=[]),
    )
    return await patch_test_structure_element_spec(conn, project_key, spec_key, spec_update)
