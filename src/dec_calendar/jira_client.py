from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

import requests
from requests.auth import HTTPBasicAuth

from dec_calendar.config import Settings
from dec_calendar.models import CalendarEventDraft, EventKind, JiraCalendarIssue, StatusCategory

logger = logging.getLogger(__name__)


class JiraClientError(RuntimeError):
    pass


class JiraAuthenticationError(JiraClientError):
    pass


def text_to_adf(text: str) -> dict[str, Any]:
    """Convert plain text (possibly multiline) to Atlassian Document Format."""
    paragraphs: list[dict[str, Any]] = []
    for line in text.split("\n"):
        paragraphs.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": line}] if line else [],
            }
        )
    if not paragraphs:
        paragraphs = [{"type": "paragraph", "content": []}]
    return {"type": "doc", "version": 1, "content": paragraphs}


class JiraClient:
    def __init__(self, settings: Settings) -> None:
        settings.require_jira()
        self.settings = settings
        self.base_url = settings.jira_url
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(settings.jira_email, settings.jira_api_token)
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
        self.session.verify = settings.jira_ssl_verify
        if not self.session.verify:
            logger.warning("Jira SSL verification disabled (JIRA_SSL_VERIFY=false)")

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
        timeout: int = 45,
    ) -> Any:
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.request(
                method,
                url,
                params=params,
                json=json_body,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise JiraClientError(f"Jira request failed: {exc}") from exc

        if response.status_code == 401:
            raise JiraAuthenticationError("Jira authentication failed — check email/token")
        if response.status_code >= 400:
            raise JiraClientError(
                f"Jira API error HTTP {response.status_code}: {response.text[:800]}"
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def get_myself(self) -> dict[str, Any]:
        return self._request("GET", "/rest/api/3/myself")

    def get_project(self, project_key: Optional[str] = None) -> dict[str, Any]:
        key = project_key or self.settings.jira_project_key
        return self._request("GET", f"/rest/api/3/project/{key}")

    def create_issue_from_draft(self, draft: CalendarEventDraft) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "project": {"key": self.settings.jira_project_key},
            "summary": draft.summary,
            "issuetype": {"name": self.settings.jira_issue_type},
            "description": text_to_adf(draft.description),
            "labels": draft.labels,
        }
        if draft.due_date is not None and not draft.needs_date:
            fields["duedate"] = draft.due_date.isoformat()
        payload = {"fields": fields}
        logger.info("Creating issue: %s", draft.summary)
        return self._request("POST", "/rest/api/3/issue", json_body=payload)

    def update_issue_fields(self, issue_key: str, fields: dict[str, Any]) -> None:
        """PATCH issue fields (e.g. duedate, description, labels)."""
        logger.info("Updating issue %s fields=%s", issue_key, sorted(fields.keys()))
        self._request("PUT", f"/rest/api/3/issue/{issue_key}", json_body={"fields": fields})

    def add_comment(self, issue_key: str, body: str) -> dict[str, Any]:
        payload = {"body": text_to_adf(body)}
        return self._request("POST", f"/rest/api/3/issue/{issue_key}/comment", json_body=payload)

    def search_all(
        self,
        jql: str,
        *,
        fields: Optional[list[str]] = None,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """Paginate /rest/api/3/search/jql until exhausted."""
        field_list = fields or [
            "summary",
            "labels",
            "duedate",
            "status",
            "issuetype",
        ]
        issues: list[dict[str, Any]] = []
        next_page_token: Optional[str] = None
        while True:
            body: dict[str, Any] = {
                "jql": jql,
                "maxResults": max_results,
                "fields": field_list,
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token
            result = self._request("POST", "/rest/api/3/search/jql", json_body=body)
            batch = result.get("values") or result.get("issues") or []
            issues.extend(batch)
            next_page_token = result.get("nextPageToken")
            # Prefer nextPageToken; do not assume isLast=True when the key is missing.
            if not next_page_token or result.get("isLast") is True:
                break
        return issues

    def delete_issue(self, issue_key: str, *, delete_subtasks: bool = True) -> None:
        params = {"deleteSubtasks": "true" if delete_subtasks else "false"}
        logger.info("Deleting issue: %s", issue_key)
        self._request("DELETE", f"/rest/api/3/issue/{issue_key}", params=params)

    def list_importable_issues(self) -> list[dict[str, Any]]:
        jql = (
            f"project = {self.settings.jira_project_key} "
            f"AND labels in (calendar-holiday, calendar-promo, calendar-birthday, needs-date)"
        )
        return self.search_all(jql, max_results=100)

    def find_by_summary(
        self,
        summary: str,
        *,
        cache: Optional[list[dict[str, Any]]] = None,
    ) -> Optional[dict[str, Any]]:
        """Exact summary match in DEC (client-side; JQL ~ is fuzzy)."""
        issues = cache if cache is not None else self.list_importable_issues()
        for issue in issues:
            if (issue.get("fields") or {}).get("summary") == summary:
                return issue
        return None

    def list_calendar_issues(self) -> list[JiraCalendarIssue]:
        jql = (
            f"project = {self.settings.jira_project_key} "
            f"AND labels in (calendar-holiday, calendar-promo, calendar-birthday) "
            f"AND duedate is not EMPTY "
            f"AND statusCategory != Done"
        )
        raw = self.search_all(jql)
        out: list[JiraCalendarIssue] = []
        for item in raw:
            parsed = self._to_calendar_issue(item)
            if parsed is not None:
                out.append(parsed)
        return out

    def _to_calendar_issue(self, item: dict[str, Any]) -> Optional[JiraCalendarIssue]:
        key = item.get("key")
        fields = item.get("fields") or {}
        if not key:
            return None
        labels = list(fields.get("labels") or [])
        kind = EventKind.from_labels(labels)
        if kind is None:
            return None
        due_raw = fields.get("duedate")
        if not due_raw:
            return None
        due = date.fromisoformat(due_raw[:10])
        summary = fields.get("summary") or key
        status_obj = fields.get("status") or {}
        status_name = str(status_obj.get("name") or "")
        cat_key = str((status_obj.get("statusCategory") or {}).get("key") or "new")
        try:
            status_category = StatusCategory(cat_key)
        except ValueError:
            status_category = StatusCategory.NEW
        return JiraCalendarIssue(
            key=key,
            summary=summary,
            kind=kind,
            due_date=due,
            labels=tuple(labels),
            browse_url=f"{self.settings.jira_browse_base}/{key}",
            status_name=status_name,
            status_category=status_category,
        )
