from __future__ import annotations

from abc import ABC, abstractmethod

from nethub_runtime.core.models import InstallRequirement, RuntimeProfile


class BaseInstaller(ABC):
    @abstractmethod
    def supports(self, requirement: InstallRequirement) -> bool:
        raise NotImplementedError

    @abstractmethod
    def install(self, requirement: InstallRequirement, profile: RuntimeProfile) -> str:
        raise NotImplementedError
