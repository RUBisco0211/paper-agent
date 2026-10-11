from uuid import UUID

from ..auth.repo import AuthRepository
from ..platform.config import settings
from ..platform.errors import ConflictError, ErrorCode, NotFoundError, ValidationError
from ..projects.repo import ProjectRepository
from ..sessions.repo import SessionBindingRepository
from .domain import weekly_cron
from .ports import AgentScheduleGateway
from .repo import ScheduleBindingRecord, ScheduleBindingRepository


class ScheduleBindingService:
    def __init__(
        self,
        schedules: ScheduleBindingRepository,
        sessions: SessionBindingRepository,
        projects: ProjectRepository,
        users: AuthRepository,
    ) -> None:
        self._schedules = schedules
        self._sessions = sessions
        self._projects = projects
        self._users = users

    def create(
        self,
        *,
        schedule_id: str,
        user_id: UUID,
        project_id: UUID | None,
    ) -> ScheduleBindingRecord:
        if project_id is not None:
            project = self._projects.get_project(project_id)
            if project is None or project.user_id != user_id:
                raise NotFoundError("项目不存在", code=ErrorCode.PROJECT_NOT_FOUND)
        if self._schedules.get(schedule_id) is not None:
            raise ConflictError("定时任务已绑定", code=ErrorCode.CONFLICT)
        record = self._schedules.add(schedule_id, user_id, project_id)
        self._schedules.commit()
        return record

    def list_for_user(self, *, user_id: UUID) -> list[ScheduleBindingRecord]:
        return self._schedules.list_for_user(user_id)

    def delete(self, *, schedule_id: str, user_id: UUID) -> None:
        record = self._schedules.get(schedule_id)
        if record is None or record.user_id != user_id:
            raise NotFoundError("定时任务不存在", code=ErrorCode.NOT_FOUND)
        self._schedules.delete(record)
        self._schedules.commit()

    def ensure_run_scope(
        self,
        *,
        schedule_id: str,
        session_id: UUID,
        user_id: UUID,
    ) -> ScheduleBindingRecord:
        task = self._schedules.get(schedule_id)
        if task is None or task.user_id != user_id:
            raise NotFoundError("定时任务不存在", code=ErrorCode.NOT_FOUND)
        if task.project_id is not None:
            project = self._projects.get_project(task.project_id)
            if project is None or project.user_id != user_id:
                raise NotFoundError("项目不存在", code=ErrorCode.PROJECT_NOT_FOUND)
        binding = self._sessions.add_scheduled_if_absent(
            session_id=session_id,
            user_id=user_id,
            project_id=task.project_id,
            schedule_id=schedule_id,
        )
        if (
            binding.user_id != user_id
            or binding.project_id != task.project_id
            or binding.schedule_id != schedule_id
        ):
            raise ConflictError("会话范围冲突", code=ErrorCode.CONFLICT)
        self._sessions.commit()
        return task

    def create_for_agent(
        self,
        *,
        gateway: AgentScheduleGateway,
        user_id: UUID,
        agent_id: str,
        session_id: UUID,
        name: str,
        prompt: str,
        time: str,
        weekdays: list[str],
    ) -> tuple[ScheduleBindingRecord, str, str]:
        scope = self._sessions.get(session_id)
        if scope is None or scope.user_id != user_id:
            raise NotFoundError("会话不存在", code=ErrorCode.SESSION_NOT_FOUND)
        if scope.project_id is not None:
            project = self._projects.get_project(scope.project_id)
            if project is None or project.user_id != user_id:
                raise NotFoundError("项目不存在", code=ErrorCode.PROJECT_NOT_FOUND)
        timezone = (
            self._users.get_timezone(user_id) or settings.schedule_default_timezone
        )
        try:
            cron = weekly_cron(time=time, weekdays=weekdays, timezone=timezone)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        schedule_id = gateway.create_disabled(
            user_id=str(user_id),
            agent_id=agent_id,
            session_id=session_id.hex,
            name=name.strip(),
            prompt=prompt.strip(),
            cron_expression=cron,
            timezone=timezone,
        )
        bound = False
        try:
            record = self.create(
                schedule_id=schedule_id,
                user_id=user_id,
                project_id=scope.project_id,
            )
            bound = True
            gateway.enable(user_id=str(user_id), schedule_id=schedule_id)
            return record, cron, timezone
        except Exception as cause:
            try:
                gateway.delete(user_id=str(user_id), schedule_id=schedule_id)
                if bound:
                    self.delete(schedule_id=schedule_id, user_id=user_id)
            except Exception as cleanup_error:
                raise ExceptionGroup(
                    "创建定时任务失败且清理未完成", [cause, cleanup_error]
                ) from cause
            raise
