from __future__ import annotations

from ..models import JobPosting


def job_summary_lines(job: JobPosting) -> list[str]:
    apply_url = job.best_apply_url or job.link
    lines = [
        f"Company: {job.company}",
        f"Role: {job.title}",
        f"Location: {job.location}",
    ]
    if job.rank_score is not None:
        lines.append(f"Score: {job.rank_score}")
    if job.rank_reason:
        lines.append(f"Why: {job.rank_reason}")
    if apply_url:
        lines.append(f"Best apply link: {apply_url}")
    if job.original_job_url and job.original_job_url != apply_url:
        lines.append(f"Original job link: {job.original_job_url}")
    if job.link_confidence:
        lines.append(f"Link confidence: {job.link_confidence}")
    if job.link_source:
        lines.append(f"Link source: {job.link_source}")
    return lines
