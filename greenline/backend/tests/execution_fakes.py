from collections.abc import Callable

import runner


class FunctionExecutionAdapter:
    def __init__(
        self,
        execute: Callable[
            [runner.ChallengeRun, runner.OutputCallback | None],
            runner.ChallengeRunResult,
        ],
    ) -> None:
        self._execute = execute

    def execute(
        self,
        run: runner.ChallengeRun,
        *,
        on_output: runner.OutputCallback | None = None,
    ) -> runner.ChallengeRunResult:
        return self._execute(run, on_output)
