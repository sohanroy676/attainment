from typing import Any

from django.db import models

from .context import get_current_college_id


class TenantQuerySet(models.QuerySet[Any]):
    pass


class TenantManager(models.Manager[Any]):
    """Always filters by the current college; with none set it returns nothing."""

    def get_queryset(self) -> TenantQuerySet:
        queryset = TenantQuerySet(self.model, using=self._db)
        college_id = get_current_college_id()
        if college_id is None:
            return queryset.none()
        return queryset.filter(college_id=college_id)


class CollegeManager(models.Manager[Any]):
    """The college table is the tenant root: it filters on its own id."""

    def get_queryset(self) -> models.QuerySet[Any]:
        queryset = super().get_queryset()
        college_id = get_current_college_id()
        if college_id is None:
            return queryset.none()
        return queryset.filter(id=college_id)
